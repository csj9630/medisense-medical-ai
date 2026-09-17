"""비교 UI와 회귀 테스트를 위한 명시적 Mock Provider입니다."""

import asyncio
from dataclasses import dataclass

from ai.llm.contracts import (
    LlmModelDefinition,
    LlmProviderUnavailableError,
    ProviderAvailability,
    ProviderGenerateRequest,
    ProviderGenerateResult,
)


@dataclass(frozen=True)
class MockFixture:
    answer: str
    delay_seconds: float
    output_tokens: int
    should_fail: bool = False


MOCK_FIXTURES = {
    "medgemma": MockFixture(
        answer=(
            "제공된 정보만으로 확정적인 진단을 내리기보다 증상의 지속 기간, "
            "복용 약물, 기저질환을 우선 확인해야 합니다. 위험 신호가 있다면 "
            "의료기관 평가를 권고하고 답변의 한계를 명확히 표시합니다."
        ),
        delay_seconds=1.6,
        output_tokens=186,
    ),
    "gemma": MockFixture(
        answer=(
            "문서의 핵심 근거를 증상, 검사 결과, 주의사항 순서로 정리합니다. "
            "문서에 없는 내용을 추가하지 않고 필요한 경우 전문가 상담을 안내합니다."
        ),
        delay_seconds=2.35,
        output_tokens=154,
    ),
    "qwen": MockFixture(
        answer=(
            "질문과 관련된 문서 조각을 선별한 뒤 반복되는 근거를 중심으로 답변을 "
            "구성합니다. 충돌하는 내용은 확인이 필요한 항목으로 구분합니다."
        ),
        delay_seconds=1.85,
        output_tokens=203,
    ),
    "llama": MockFixture(
        answer="",
        delay_seconds=2.65,
        output_tokens=0,
        should_fail=True,
    ),
}


class MockLlmProvider:
    key = "mock"
    is_mock = True

    async def check_availability(
        self,
        model: LlmModelDefinition,
    ) -> ProviderAvailability:
        available = model.provider_model in MOCK_FIXTURES
        return ProviderAvailability(
            available,
            None if available else "Mock fixture가 등록되지 않았습니다.",
        )

    async def generate(
        self,
        request: ProviderGenerateRequest,
        model: LlmModelDefinition,
    ) -> ProviderGenerateResult:
        fixture = MOCK_FIXTURES.get(model.provider_model)
        if fixture is None:
            raise LlmProviderUnavailableError(
                f"Mock fixture가 없습니다: {model.provider_model}"
            )

        await asyncio.sleep(fixture.delay_seconds)
        if fixture.should_fail:
            raise LlmProviderUnavailableError(
                "Mock Provider가 일시적으로 응답하지 않았습니다."
            )

        input_tokens = max(
            64,
            round(len(request.joined_content().strip()) * 1.7)
            + (18 if request.document_name else 0),
        )
        reference_note = (
            f" 참고 문서({request.document_name})는 파일명 조건만 반영한 Mock입니다."
            if request.document_name
            else " 참고 문서 없이 실행한 Mock 결과입니다."
        )
        return ProviderGenerateResult(
            answer=f"{fixture.answer}{reference_note}",
            input_tokens=input_tokens,
            output_tokens=fixture.output_tokens,
            total_tokens=input_tokens + fixture.output_tokens,
            finish_reason="mock",
        )
