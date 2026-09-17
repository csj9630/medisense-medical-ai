"""Bearer 인증을 사용하는 원격 LLM 추론 API 공통 Provider입니다."""

import asyncio
from collections.abc import Callable
from typing import Any

import httpx

from ai.llm.contracts import (
    LlmModelDefinition,
    LlmProviderAuthenticationError,
    LlmProviderRateLimitError,
    LlmProviderTimeoutError,
    LlmProviderUnavailableError,
    LlmUpstreamError,
    ProviderAvailability,
    ProviderGenerateRequest,
    ProviderGenerateResult,
)


class RemoteHttpLlmProvider:
    key = "remote-http"
    is_mock = False
    _redirect_message = (
        "원격 접속 URL이 로그인 또는 다른 페이지로 연결됩니다. "
        "Vast.ai 인스턴스의 공개 HTTP Endpoint와 포트를 확인하세요."
    )

    def __init__(
        self,
        *,
        enabled: bool,
        base_url: str,
        api_key: str | None,
        timeout_seconds: float,
        max_concurrency: int,
        transport: httpx.AsyncBaseTransport | None = None,
        client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient,
    ) -> None:
        self._enabled = enabled
        self._base_url = base_url.strip().rstrip("/")
        self._api_key = api_key.strip() if api_key else None
        self._timeout_seconds = max(1.0, timeout_seconds)
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self._transport = transport
        self._client_factory = client_factory

    def _client(self, *, availability: bool = False) -> httpx.AsyncClient:
        total_timeout = min(5.0, self._timeout_seconds) if availability else self._timeout_seconds
        return self._client_factory(
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=httpx.Timeout(
                total_timeout,
                connect=min(3.0 if availability else 10.0, total_timeout),
            ),
            transport=self._transport,
        )

    def _configuration_error(self) -> str | None:
        if not self._enabled:
            return "원격 LLM Provider가 비활성화되었습니다."
        if not self._base_url:
            return "LLM_REMOTE_BASE_URL이 설정되지 않았습니다."
        if not self._api_key:
            return "LLM_REMOTE_API_KEY가 설정되지 않았습니다."
        return None

    async def check_availability(self, model: LlmModelDefinition) -> ProviderAvailability:
        configuration_error = self._configuration_error()
        if configuration_error:
            return ProviderAvailability(False, configuration_error)

        try:
            async with self._client(availability=True) as client:
                response = await client.get(f"{self._base_url}/health")
        except (httpx.TimeoutException, httpx.RequestError):
            return ProviderAvailability(False, "원격 추론 서버에 연결할 수 없습니다.")

        if response.status_code in (401, 403):
            return ProviderAvailability(False, "원격 추론 API 인증에 실패했습니다.")
        if response.is_redirect:
            return ProviderAvailability(False, self._redirect_message)
        if response.status_code != 200:
            return ProviderAvailability(
                False,
                f"원격 모델 상태를 확인하지 못했습니다. (HTTP {response.status_code})",
            )

        try:
            payload = response.json()
        except ValueError:
            return ProviderAvailability(False, "원격 상태 응답 형식이 올바르지 않습니다.")
        if not isinstance(payload, dict):
            return ProviderAvailability(False, "원격 상태 응답 형식이 올바르지 않습니다.")
        models = payload.get("models", [])
        if not isinstance(models, list) or model.provider_model not in models:
            return ProviderAvailability(
                False,
                f"원격 서버에 모델이 로드되지 않았습니다: {model.provider_model}",
            )
        return ProviderAvailability(True)

    async def generate(
        self,
        request: ProviderGenerateRequest,
        model: LlmModelDefinition,
    ) -> ProviderGenerateResult:
        configuration_error = self._configuration_error()
        if configuration_error:
            raise LlmProviderUnavailableError(configuration_error)

        payload: dict[str, Any] = {
            "model": model.provider_model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in request.messages
            ],
        }
        if request.max_output_tokens is not None:
            payload["max_output_tokens"] = request.max_output_tokens

        try:
            async with self._semaphore:
                async with self._client() as client:
                    response = await client.post(f"{self._base_url}/v1/generate", json=payload)
        except httpx.TimeoutException as exc:
            raise LlmProviderTimeoutError("원격 추론 응답 제한시간을 초과했습니다.") from exc
        except httpx.RequestError as exc:
            raise LlmProviderUnavailableError(
                "원격 추론 서버에 연결할 수 없습니다."
            ) from exc

        if response.status_code in (401, 403):
            raise LlmProviderAuthenticationError("원격 추론 API 인증에 실패했습니다.")
        if response.is_redirect:
            raise LlmProviderUnavailableError(self._redirect_message)
        if response.status_code == 404:
            raise LlmProviderUnavailableError(
                f"원격 서버에 모델이 로드되지 않았습니다: {model.provider_model}"
            )
        if response.status_code == 429:
            raise LlmProviderRateLimitError("원격 서버가 현재 요청을 더 받을 수 없습니다.")
        if response.status_code >= 500:
            raise LlmUpstreamError("원격 모델 실행 중 오류가 발생했습니다.")
        if response.status_code >= 400:
            raise LlmUpstreamError("원격 추론 요청을 처리하지 못했습니다.")

        try:
            data = response.json()
        except ValueError as exc:
            raise LlmUpstreamError("원격 추론 응답 형식이 올바르지 않습니다.") from exc
        if not isinstance(data, dict):
            raise LlmUpstreamError("원격 추론 응답 형식이 올바르지 않습니다.")
        answer = data.get("answer", "")
        if not isinstance(answer, str) or not answer.strip():
            raise LlmUpstreamError("원격 모델이 빈 답변을 반환했습니다.")

        input_tokens = self._optional_int(data.get("input_tokens"))
        output_tokens = self._optional_int(data.get("output_tokens"))
        total_tokens = self._optional_int(data.get("total_tokens"))
        if total_tokens is None and input_tokens is not None and output_tokens is not None:
            total_tokens = input_tokens + output_tokens
        finish_reason = data.get("finish_reason")
        return ProviderGenerateResult(
            answer=answer.strip(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            finish_reason=finish_reason if isinstance(finish_reason, str) else None,
        )

    @staticmethod
    def _optional_int(value: object) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) else None
