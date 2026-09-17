from unittest.mock import AsyncMock

from ai.llm import (
    LlmMessage,
    LlmModelDefinition,
    ProviderAvailability,
    ProviderGenerateRequest,
    ProviderGenerateResult,
)


def model_definition(
    *,
    model_id: str = "gemma",
    provider_key: str = "ollama",
    provider_model: str = "gemma3:1b",
    group: str = "main",
) -> LlmModelDefinition:
    return LlmModelDefinition(
        id=model_id,
        label=model_id,
        family="test",
        training_stage="test",
        description="test",
        group=group,  # type: ignore[arg-type]
        provider_key=provider_key,
        provider_model=provider_model,
    )


def prompt_request(prompt: str = "질문") -> ProviderGenerateRequest:
    return ProviderGenerateRequest(
        messages=(LlmMessage(role="user", content=prompt),)
    )


class FakeProvider:
    def __init__(self, key: str, *, is_mock: bool = False) -> None:
        self.key = key
        self.is_mock = is_mock
        self.generate = AsyncMock(
            return_value=ProviderGenerateResult(
                answer=f"{key} answer",
                input_tokens=10,
                output_tokens=20,
                total_tokens=30,
                finish_reason="stop",
            )
        )

    async def check_availability(self, model: LlmModelDefinition) -> ProviderAvailability:
        del model
        return ProviderAvailability(True)
