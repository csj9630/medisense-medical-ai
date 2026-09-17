"""로컬 Ollama Chat API Provider입니다."""

import asyncio
from collections.abc import Callable
from typing import Any

import httpx

from ai.llm.contracts import (
    LlmModelDefinition,
    LlmProviderRateLimitError,
    LlmProviderTimeoutError,
    LlmProviderUnavailableError,
    LlmUpstreamError,
    ProviderAvailability,
    ProviderGenerateRequest,
    ProviderGenerateResult,
)


class OllamaLlmProvider:
    key = "ollama"
    is_mock = False

    def __init__(
        self,
        *,
        enabled: bool,
        base_url: str,
        timeout_seconds: float,
        max_concurrency: int,
        transport: httpx.AsyncBaseTransport | None = None,
        client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient,
    ) -> None:
        self._enabled = enabled
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = max(1.0, timeout_seconds)
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self._transport = transport
        self._client_factory = client_factory

    def _client(self, *, availability: bool = False) -> httpx.AsyncClient:
        total_timeout = min(3.0, self._timeout_seconds) if availability else self._timeout_seconds
        return self._client_factory(
            timeout=httpx.Timeout(
                total_timeout,
                connect=min(2.0 if availability else 10.0, total_timeout),
            ),
            transport=self._transport,
        )

    async def check_availability(self, model: LlmModelDefinition) -> ProviderAvailability:
        if not self._enabled:
            return ProviderAvailability(False, "Ollama Provider가 비활성화되었습니다.")
        try:
            async with self._client(availability=True) as client:
                response = await client.get(f"{self._base_url}/api/tags")
        except (httpx.TimeoutException, httpx.RequestError):
            return ProviderAvailability(False, "Ollama에 연결할 수 없습니다. Ollama 실행 상태를 확인하세요.")
        if response.status_code != 200:
            return ProviderAvailability(False, "Ollama 모델 목록을 확인하지 못했습니다.")
        try:
            payload = response.json()
            names = {
                value
                for item in payload.get("models", [])
                if isinstance(item, dict)
                for value in (item.get("name"), item.get("model"))
                if isinstance(value, str)
            }
        except (TypeError, ValueError):
            return ProviderAvailability(False, "Ollama 응답 형식이 올바르지 않습니다.")
        if not self._contains_model(names, model.provider_model):
            return ProviderAvailability(False, f"Ollama 모델이 설치되지 않았습니다: {model.provider_model}")
        return ProviderAvailability(True)

    @staticmethod
    def _contains_model(names: set[str], configured_model: str) -> bool:
        return configured_model in names or (
            ":" not in configured_model and f"{configured_model}:latest" in names
        )

    async def generate(
        self,
        request: ProviderGenerateRequest,
        model: LlmModelDefinition,
    ) -> ProviderGenerateResult:
        if not self._enabled:
            raise LlmProviderUnavailableError("Ollama Provider가 비활성화되었습니다.")

        # Core Message의 role과 순서를 Ollama Chat API에 그대로 전달합니다.
        messages = [
            {"role": message.role, "content": message.content}
            for message in request.messages
        ]
        payload: dict[str, Any] = {
            "model": model.provider_model,
            "messages": messages,
            "stream": False,
        }
        if request.max_output_tokens is not None:
            payload["options"] = {"num_predict": request.max_output_tokens}
        try:
            async with self._semaphore:
                async with self._client() as client:
                    response = await client.post(f"{self._base_url}/api/chat", json=payload)
        except httpx.TimeoutException as exc:
            raise LlmProviderTimeoutError("Ollama 응답 제한시간을 초과했습니다.") from exc
        except httpx.RequestError as exc:
            raise LlmProviderUnavailableError("Ollama에 연결할 수 없습니다. Ollama 실행 상태를 확인하세요.") from exc
        if response.status_code == 404:
            raise LlmProviderUnavailableError(
                f"Ollama 모델이 설치되지 않았습니다: {model.provider_model}. "
                f"ollama pull {model.provider_model} 명령을 실행하세요."
            )
        if response.status_code == 429:
            raise LlmProviderRateLimitError("Ollama가 현재 요청을 너무 많이 받고 있습니다.")
        if response.status_code >= 500:
            raise LlmUpstreamError("Ollama 모델 실행 중 오류가 발생했습니다.")
        if response.status_code >= 400:
            raise LlmUpstreamError("Ollama 요청을 처리하지 못했습니다.")
        try:
            data = response.json()
            message = data.get("message")
            answer = message.get("content", "") if isinstance(message, dict) else ""
        except (TypeError, ValueError) as exc:
            raise LlmUpstreamError("Ollama 응답 형식이 올바르지 않습니다.") from exc
        if not isinstance(answer, str) or not answer.strip():
            raise LlmUpstreamError("Ollama가 빈 답변을 반환했습니다.")
        input_tokens = self._optional_int(data.get("prompt_eval_count"))
        output_tokens = self._optional_int(data.get("eval_count"))
        total_tokens = input_tokens + output_tokens if input_tokens is not None and output_tokens is not None else None
        finish_reason = data.get("done_reason")
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
