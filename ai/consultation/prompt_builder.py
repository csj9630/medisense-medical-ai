"""system_prompt.md + [진료과 분류 결과] + [참고 의료 정보] + [사용자 질문]을
`ai.llm`이 바로 받을 수 있는 `LlmMessage` 튜플로 조립한다.

여기서 조립을 끝내고 나면 그 뒤(LLM 호출, 응답에 면책 문구 붙이기)는 이 파일의
책임이 아니다 — pipeline.py 참고.
"""
from functools import lru_cache
from pathlib import Path

from ai.llm.contracts import LlmMessage

from .classifier import DepartmentResult

_SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / "system_prompt.md"


@lru_cache(maxsize=1)
def _load_system_prompt() -> str:
    return _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def _department_block(result: DepartmentResult | None) -> str | None:
    """진료과 참고정보를 "[진료과 분류 결과]" 같은 대괄호 라벨 블록이 아니라 괄호로 감싼
    지시문 형태로 만들었었다 — 소형 모델이 대괄호 라벨을 데이터 헤더로 착각해서 답변에
    그대로 되풀이하는 문제가 있었다(라벨을 없애니 재현되지 않음). 그런데 그 대신 이번엔
    힌트 자체를 괄호로 감싸다 보니, 모델이 "괄호로 감싸는 스타일"을 그대로 따라 해서
    "(정형외과에서 진료를 받아보시는 것도 고려해볼 수 있습니다.)"처럼 답변 마지막 문장
    전체를 괄호로 감싸버리는 새 문제가 생겼다(실제 채팅에서 관찰됨). 그래서 힌트 자체는
    괄호로 감싸지 않는 평문으로 바꾸고, "답변에서도 괄호로 감싸지 말라"는 지시를 명시로
    추가했다(response_validator.py에 안전장치도 별도로 둠)."""
    if result is None or result.department is None:
        return None
    return (
        f"참고용 진료과 정보 - {result.department} 관련 가능성, 신뢰도 {result.confidence}. "
        "이 정보는 답변 마지막 문장에 괄호나 따옴표로 따로 묶지 말고, 자연스러운 문장의 "
        "일부로 한 번만 녹여서 언급하세요. 이 문장 형식 자체를 답변에 그대로 옮기지 마세요."
    )


def build_messages(
    user_question: str,
    *,
    history: tuple[LlmMessage, ...] = (),
    department_result: DepartmentResult | None = None,
    reference_info_block: str | None = None,
) -> tuple[LlmMessage, ...]:
    """이전 대화의 역할과 순서를 보존하고 마지막에 현재 질문을 한 번만 추가한다."""
    sections: list[str] = []

    department_block = _department_block(department_result)
    if department_block:
        sections.append(department_block)

    if reference_info_block:
        sections.append(reference_info_block)

    sections.append(f"[사용자 질문]\n{user_question.strip()}")

    return (
        LlmMessage(role="system", content=_load_system_prompt()),
        *history,
        LlmMessage(role="user", content="\n\n".join(sections)),
    )
