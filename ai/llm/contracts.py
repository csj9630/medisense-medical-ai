"""LLM Core와 Provider가 공유하는 Framework 독립 계약입니다."""

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class LlmMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class LlmModelDefinition:
    id: str
    label: str
    family: str
    training_stage: str
    description: str
    group: Literal["main", "other"]
    provider_key: str
    provider_model: str
    enabled: bool = True


@dataclass(frozen=True)
class ProviderGenerateRequest:
    messages: tuple[LlmMessage, ...]
    document_name: str | None = None
    max_output_tokens: int | None = None

    @classmethod
    def from_prompt(
        cls,
        prompt: str,
        *,
        document_name: str | None = None,
        max_output_tokens: int | None = None,
    ) -> "ProviderGenerateRequest":
        """단일 Prompt 기반 호출을 공통 Message 계약으로 변환합니다."""

        return cls(
            messages=(LlmMessage(role="user", content=prompt),),
            document_name=document_name,
            max_output_tokens=max_output_tokens,
        )

    def joined_content(self) -> str:
        """Mock 통계처럼 Message 전체 문자열이 필요한 경우에만 사용합니다."""

        return "\n".join(message.content for message in self.messages)


@dataclass(frozen=True)
class ProviderGenerateResult:
    answer: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    finish_reason: str | None = None


@dataclass(frozen=True)
class ProviderAvailability:
    available: bool
    message: str | None = None


@dataclass(frozen=True)
class LlmExecutionResult:
    definition: LlmModelDefinition
    provider: str
    is_mock: bool
    result: ProviderGenerateResult
    response_time_seconds: float


@dataclass(frozen=True)
class LlmModelCatalogEntry:
    definition: LlmModelDefinition
    provider: str
    is_mock: bool
    availability: ProviderAvailability


class LlmProvider(Protocol):
    key: str
    is_mock: bool

    async def generate(
        self,
        request: ProviderGenerateRequest,
        model: LlmModelDefinition,
    ) -> ProviderGenerateResult: ...

    async def check_availability(
        self,
        model: LlmModelDefinition,
    ) -> ProviderAvailability: ...


class LlmServiceError(Exception):
    """외부 응답에 안전하게 변환할 수 있는 LLM Domain 오류입니다."""

    status_code = 502


class UnknownLlmModelError(LlmServiceError):
    status_code = 422


class LlmProviderUnavailableError(LlmServiceError):
    status_code = 503


class LlmProviderTimeoutError(LlmServiceError):
    status_code = 504


class LlmProviderAuthenticationError(LlmServiceError):
    status_code = 503


class LlmProviderRateLimitError(LlmServiceError):
    status_code = 429


class LlmContentBlockedError(LlmServiceError):
    status_code = 422


class LlmUpstreamError(LlmServiceError):
    status_code = 502
