"""ChuGyouk/GenMedGPT-5k-ko 어댑터.

실제 필드(STEP 0 확인 결과): instruction, output, input.
언뜻 Alpaca 스타일 같지만 다른 어댑터들과 성격이 다르다 - instruction이 매 행
"당신이 의사라면 환자의 설명을 바탕으로 의학적 질문에 답변해 주세요." 같은 고정
역할 지시문(prompt template)이고, 실제 환자 증상/질문은 input에, 의사의 답변은
output에 들어있다. instruction은 dataset-specific prompt template 그 자체라서
명세가 명시적으로 제거하라는 대상 - content에 넣지 않는다.

department 채우기: 이 데이터셋엔 별도 카테고리 필드가 없지만, output(의사 답변)에
가끔 진료과 이름이 그대로 등장한다("정형외과에서 진료를 받아보시는 것이 좋습니다"
등) - `ai/consultation/response_validator.extract_mentioned_department()`가 LLM
최종 답변에서 진료과를 뽑는 것과 같은 원리를 원본 답변 텍스트에 그대로 적용한다.
진료과 이름이 정확히 하나만 등장할 때만 채택하고(여러 개면 헷갈리는 것이므로
None), 이 데이터셋 자체가 GPT 생성 + 미검수(reliability_tier="낮음")라 잘못된
언급이 섞여 있을 수 있다는 한계는 그대로 물려받는다 - generated_metadata=True로
"원본 필드가 아니라 텍스트에서 추출한 값"임을 구분해서 남긴다.
"""
from typing import Any

from ..schema import NormalizedRecord
from .base import DatasetAdapter

SOURCE = "GenMedGPT-5k-ko"
SOURCE_TYPE = "doctor_patient_dialogue"

# ai/consultation/classifier.py의 진료과 명칭과 맞춰뒀다 - 여기서 뽑은 값이 나중에
# RAG 검색 결과로 그 분류기와 같이 쓰이므로(ai/consultation/context.py의
# derive_department_from_chunks), 명칭이 서로 다르면 다수결 집계가 갈라진다.
_DEPARTMENT_NAMES = (
    "내과", "순환기내과", "이비인후과", "피부과", "정형외과", "신경과", "안과",
    "산부인과", "비뇨의학과", "정신건강의학과", "소아청소년과",
)


def _extract_mentioned_department(text: str) -> str | None:
    # "순환기내과"가 "내과"를 부분 문자열로 포함해서, "순환기내과"만 언급돼도 substring
    # 매칭으로는 "내과"까지 같이 걸린다 - 더 구체적인(긴) 이름이 함께 걸리면 그 안에
    # 포함된 일반 이름은 제외한다(ai/consultation/response_validator.py의
    # extract_mentioned_department와 동일한 보정).
    mentioned = {name for name in _DEPARTMENT_NAMES if name in text}
    specific = {
        name for name in mentioned
        if not any(name != other and name in other for other in mentioned)
    }
    if len(specific) == 1:
        return next(iter(specific))
    return None


class GenMedGptAdapter(DatasetAdapter):
    source = SOURCE
    source_type = SOURCE_TYPE
    hf_path = "ChuGyouk/GenMedGPT-5k-ko"

    def to_normalized(self, raw_row: dict[str, Any], index: int) -> NormalizedRecord | None:
        patient_input = str(raw_row.get("input") or "").strip()
        output = str(raw_row.get("output") or "").strip()
        if not patient_input or not output:
            return None

        content = f"{patient_input}\n\n{output}"

        department_name = _extract_mentioned_department(output)
        department = [department_name] if department_name else []

        # 실제 HF dataset card 확인 결과 - ChatDoctor(GPT 생성 합성 대화)를
        # DeepL로 번역한 것. 원본도 생성 데이터고 전문가 검수 언급 없음 - 팀
        # 지시서 5-1절 "낮음" 기준.
        metadata: dict[str, Any] = {
            "language": "ko",
            "content_type": "doctor_patient_dialogue",
            "reliability": "ai_generated_unverified",
            "reliability_tier": "낮음",
            "reliability_reason": "ChatDoctor(GPT 생성 합성 대화) 원본을 DeepL로 번역, 전문가 검수 언급 없음",
            "source_tier": 3,
            "verification_status": "llm_generated_unverified",
        }
        if department:
            # 원본에 카테고리 필드가 없어서 답변 텍스트에서 뽑아낸 값이라는 걸
            # 구분해둔다(snuh_clinical_qa.py의 generated_metadata 관례와 동일).
            metadata["generated_metadata"] = True

        return NormalizedRecord(
            source=SOURCE,
            source_type=SOURCE_TYPE,
            content=content,
            original_id=str(index),
            original_dataset=self.hf_path,
            question=patient_input,
            answer=output,
            department=department,
            metadata=metadata,
        )
