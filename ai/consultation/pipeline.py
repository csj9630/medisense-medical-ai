"""RAG/분류 결과를 프롬프트로 조립해 LLM을 호출하고 응답을 검증합니다.

면책 문구는 더 이상 여기서 답변 텍스트에 붙이지 않는다 — 매 답변마다 반복되는 문구라
프론트엔드가 채팅 UI에 별도 경고 배너로 보여준다(MessageBubble.tsx 참고). 이 파일은
검증된 LLM 원문 그대로를 answer로 반환한다.

흐름:
    사용자 질문
        -> 응급 키워드 하드 필터
        -> 진료과 분류
        -> 참고 의료 정보 조립
        -> 프롬프트 조립
        -> 주입받은 LlmApplicationService 호출
        -> 응답 검증(response_validator)

이 모듈은 DB 세션과 Backend 설정을 모른다. Backend는 Admin·일반 API·채팅이
공유하는 Vast.ai 원격 LLM Application을 만들어 consult()에 주입한다.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any

from ai.llm.contracts import LlmMessage, ProviderGenerateRequest

from . import response_validator, risk_detector
from .classifier import BaseQueryClassifier, DepartmentResult, get_default_classifier
from .context import build_reference_info_block, derive_department_from_chunks
from .prompt_builder import build_messages

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ID = "medgemma"

# Vast.ai 서버(scripts/vastai_medical_llm_server.py)의 GenerateRequest.max_output_tokens
# 기본값은 256이지만 최대 512까지 지원한다. 이 값을 명시적으로 안 넘기면 서버 기본값인
# 256으로 잘려서, 공감+원인 설명+확인 질문+주의사항을 다 담는 답변이 문장 중간에
# 끊기는 게 실제로 관찰됐다(예: "...정확한 진단 후 적절한" 에서 끊김). 서버가 허용하는
# 최댓값(512)을 그대로 요청한다.
DEFAULT_MAX_OUTPUT_TOKENS = 512

FALLBACK_ANSWER = (
    "죄송합니다, 지금은 AI 상담 응답을 생성할 수 없습니다. 잠시 후 다시 시도해주시거나, "
    "증상이 계속되면 의료기관 방문을 고려해주세요."
)


@dataclass(frozen=True)
class ConsultationResult:
    answer: str
    department: str | None
    confidence: str
    # 아래는 전부 관리자 대시보드 로깅용 메타데이터다 — 호출하는 쪽(message.py)이
    # 그대로 consultation_logs에 저장한다. 새로 추가된 필드라 기본값을 둬서 기존
    # 호출부/테스트가 안 깨지게 했다.
    model_id: str | None = None
    provider_key: str | None = None
    is_fallback: bool = False
    is_emergency: bool = False
    rag_hit_count: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    response_time_ms: int | None = None
    error_type: str | None = None
    # provider가 응답을 왜 멈췄는지("stop"=정상 종료, "length"=max_output_tokens에
    # 걸려 잘림 등). 값 자체는 ai/llm/contracts.py의 ProviderGenerateResult가 이미
    # provider별로 정규화해서 채워주고 있었는데, 여기서 안 읽고 버려서 답변이
    # 잘렸는지 여부를 어디서도 추적할 수 없었다(관리자 대시보드에서 "잘림 비율"
    # 같은 지표를 낼 수 없는 gap이었음) - consultation_logs까지 그대로 흘려보낸다.
    finish_reason: str | None = None


def _resolve_department(
    department_result: DepartmentResult | None,
    *,
    classifier: BaseQueryClassifier | None,
    user_question: str,
    reference_chunks: list[Any] | None,
) -> DepartmentResult:
    """진료과를 어떤 신호로 확정할지의 우선순위.

    1. 이미 "높음" 확신으로 넘어온 분류가 있으면 그대로 유지한다 — 사용자 원문에
       키워드가 2개 이상 겹쳐서 나온 강한 신호를 RAG 문서 하나로 뒤집을 이유가
       없다. (실제로 RAG 검색이 증상과 무관한 문서를 끌어오는 사례가 관찰된 적이
       있어서, 강한 신호를 약한 신호로 덮어쓰지 않도록 보수적으로 둔다.)
    2. 그 외(분류가 없거나 "중간"/"낮음")에는 RAG로 검색된 참고 문서의 진료과
       메타데이터를 우선 확인한다 — 실제 검색된 근거 기반이라 사용자 원문 키워드
       매칭보다 신호가 강할 수 있다.
    3. RAG 신호도 없으면 기존에 있던 분류 결과(사전 분류 또는 새로 돌린 키워드
       분류)를 그대로 쓴다. 이후 LLM 호출이 성공하면 `consult()`가 답변에서
       언급된 진료과로 한 번 더 보완을 시도한다(department가 여전히 None일 때만).
    """
    if department_result is not None and department_result.confidence == "높음":
        return department_result

    rag_department = derive_department_from_chunks(reference_chunks)
    if rag_department is not None:
        return rag_department

    if department_result is not None:
        return department_result

    resolved_classifier = classifier or get_default_classifier()
    return resolved_classifier.classify(user_question)


async def consult(
    llm_application: Any,
    user_question: str,
    *,
    history: tuple[LlmMessage, ...] = (),
    model_id: str = DEFAULT_MODEL_ID,
    reference_chunks: list[Any] | None = None,
    classifier: BaseQueryClassifier | None = None,
    department_result: DepartmentResult | None = None,
) -> ConsultationResult:
    started_at = time.perf_counter()
    rag_hit_count = len(reference_chunks) if reference_chunks else 0

    # LLM 호출 전 하드 필터 — 프롬프트 지시 준수 여부와 무관하게 작동하는 이중 안전장치.
    # 응급 안전 응답을 내는 것과 진료과를 분류하는 것은 서로 다른 관심사라, 응급이어도
    # classify()는 그대로 돌린다 - 예전에는 여기서 department=None을 강제해서 응급으로
    # 잡힌 대화가 전부 관리자 화면에 "기타"로만 쌓이고, 신경과/순환기내과처럼 실제로는
    # 분류 가능했던 사례까지 통계에서 사라지는 부작용이 있었다(2026-09 실측으로 확인).
    if risk_detector.detect_emergency(user_question):
        department_result = _resolve_department(
            department_result,
            classifier=classifier,
            user_question=user_question,
            reference_chunks=reference_chunks,
        )
        return ConsultationResult(
            answer=risk_detector.EMERGENCY_RESPONSE,
            department=department_result.department,
            confidence=department_result.confidence,
            is_emergency=True,
            rag_hit_count=rag_hit_count,
            response_time_ms=round((time.perf_counter() - started_at) * 1000),
        )

    # 호출하는 쪽(message.py)이 RAG 검색의 진료과 부스트에도 같은 분류 결과를
    # 쓰려고 미리 classify()를 해뒀다면 그걸 넘겨받되, RAG 검색 결과가 실제로
    # 나온 뒤에는 `_resolve_department()`가 그 결과의 진료과 메타데이터로
    # 보정할 기회를 준다(우선순위는 위 함수 docstring 참고).
    department_result = _resolve_department(
        department_result,
        classifier=classifier,
        user_question=user_question,
        reference_chunks=reference_chunks,
    )
    reference_block = build_reference_info_block(reference_chunks)
    messages = build_messages(
        user_question,
        history=history,
        department_result=department_result,
        reference_info_block=reference_block,
    )

    provider_key: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    is_fallback = False
    error_type: str | None = None
    finish_reason: str | None = None

    try:
        execution = await llm_application.run(
            model_id,
            ProviderGenerateRequest(messages=messages, max_output_tokens=DEFAULT_MAX_OUTPUT_TOKENS),
        )
        answer = response_validator.validate(execution.result.answer.strip(), user_question=user_question)
        if not answer.strip():
            # validate()가 빈 문자열을 반환하는 건 "잘라낼 정상 답변조차 없었다"는
            # 뜻이다(예: 모델이 의료 답변 대신 자기 자신에게 주는 메타 지시문만
            # 출력한 경우, 2026-09 실측). 이런 답변은 LLM 호출 실패(except 분기)와
            # 사실상 같은 상황이므로 같은 FALLBACK_ANSWER로 대체한다 — 실제 의료
            # 정보가 아니므로 면책 문구도 붙이지 않는다.
            answer = FALLBACK_ANSWER
            is_fallback = True
            error_type = "NonAnswerFiltered"
        # 사전 분류(department_result)가 진료과를 못 짚었으면, 이미 나온 최종
        # 답변에서 LLM이 실제로 언급한 진료과로 보완한다 - 사용자 원문보다
        # RAG 참고자료까지 반영한 최종 판단이 더 신뢰도 높은 신호다(response_validator.
        # extract_mentioned_department 참고 - 답변에 진료과가 하나만 명확히
        # 나올 때만 채택하고, 모델이 헷갈려 여러 개를 나열했으면 그대로 None).
        elif department_result.department is None:
            mentioned_department = response_validator.extract_mentioned_department(answer)
            if mentioned_department:
                department_result = DepartmentResult(department=mentioned_department, confidence="중간")
        # execution/result는 호출하는 쪽이 넘겨준 llm_application 구현에 달려있어서
        # (테스트에서는 최소 stub을 쓴다), 없는 필드는 조용히 None으로 둔다 —
        # 로깅 메타데이터 때문에 LLM 호출 계약을 더 무겁게 만들지 않기 위함.
        provider_key = getattr(execution, "provider", None)
        input_tokens = getattr(execution.result, "input_tokens", None)
        output_tokens = getattr(execution.result, "output_tokens", None)
        total_tokens = getattr(execution.result, "total_tokens", None)
        finish_reason = getattr(execution.result, "finish_reason", None)
    except Exception as exc:
        # 원격 서버 중지, 모델 미로드, 인증 실패 등 어떤 이유로든 LLM 호출이
        # 실패해도 채팅 자체는 계속 동작해야 한다. 원인은 여기서 로깅하고,
        # 사용자에게는 안전한 대체 응답만 보여준다 — 이건 실제 의료 답변이
        # 아니므로 면책 문구를 붙이지 않는다.
        logger.exception("consult: LLM 호출 실패 model_id=%s", model_id)
        answer = FALLBACK_ANSWER
        is_fallback = True
        error_type = type(exc).__name__

    return ConsultationResult(
        answer=answer,
        department=department_result.department,
        confidence=department_result.confidence,
        model_id=model_id,
        provider_key=provider_key,
        is_fallback=is_fallback,
        rag_hit_count=rag_hit_count,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        response_time_ms=round((time.perf_counter() - started_at) * 1000),
        error_type=error_type,
        finish_reason=finish_reason,
    )
