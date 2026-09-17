import json
import unittest

import httpx

from ai.llm import (
    LlmMessage,
    LlmProviderAuthenticationError,
    LlmProviderUnavailableError,
    ProviderGenerateRequest,
)
from ai.llm.providers.remote_http import RemoteHttpLlmProvider
from tests.ai.llm.helpers import model_definition


def remote_definition(*, provider_model: str = "qwen"):
    return model_definition(
        model_id=provider_model,
        provider_key="remote-http",
        provider_model=provider_model,
        group="other",
    )


class RemoteHttpProviderTest(unittest.IsolatedAsyncioTestCase):
    async def test_health_and_generation_contract(self) -> None:
        captured: dict[str, object] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers["Authorization"], "Bearer test-secret")
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "ok", "models": ["qwen", "llama"]})
            captured.update(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "answer": "원격 응답",
                    "input_tokens": 12,
                    "output_tokens": 34,
                    "finish_reason": "stop",
                },
            )

        provider = RemoteHttpLlmProvider(
            enabled=True,
            base_url="https://vast.example/",
            api_key="test-secret",
            timeout_seconds=30,
            max_concurrency=1,
            transport=httpx.MockTransport(handler),
        )
        request = ProviderGenerateRequest(
            messages=(
                LlmMessage(role="system", content="근거만 답변"),
                LlmMessage(role="user", content="질문"),
            ),
            max_output_tokens=200,
        )

        availability = await provider.check_availability(remote_definition())
        result = await provider.generate(request, remote_definition())

        self.assertTrue(availability.available)
        self.assertEqual(captured["model"], "qwen")
        self.assertEqual(captured["max_output_tokens"], 200)
        self.assertEqual(
            [message["role"] for message in captured["messages"]],  # type: ignore[index]
            ["system", "user"],
        )
        self.assertEqual(result.answer, "원격 응답")
        self.assertEqual((result.input_tokens, result.output_tokens, result.total_tokens), (12, 34, 46))

    async def test_missing_configuration_is_unavailable_without_network(self) -> None:
        provider = RemoteHttpLlmProvider(
            enabled=True,
            base_url="",
            api_key=None,
            timeout_seconds=30,
            max_concurrency=1,
        )

        availability = await provider.check_availability(remote_definition())

        self.assertFalse(availability.available)
        self.assertIn("LLM_REMOTE_BASE_URL", availability.message or "")

    async def test_authentication_error_does_not_expose_api_key(self) -> None:
        provider = RemoteHttpLlmProvider(
            enabled=True,
            base_url="https://vast.example",
            api_key="never-expose-this",
            timeout_seconds=30,
            max_concurrency=1,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(401, json={"detail": "unauthorized"})
            ),
        )

        with self.assertRaises(LlmProviderAuthenticationError) as raised:
            await provider.generate(
                ProviderGenerateRequest.from_prompt("질문"),
                remote_definition(provider_model="llama"),
            )

        self.assertNotIn("never-expose-this", str(raised.exception))

    async def test_login_redirect_reports_endpoint_configuration_error(self) -> None:
        provider = RemoteHttpLlmProvider(
            enabled=True,
            base_url="https://machine.vast.example",
            api_key="test-secret",
            timeout_seconds=30,
            max_concurrency=1,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    302,
                    headers={"Location": "https://console.vast.ai/auth/signin"},
                )
            ),
        )

        availability = await provider.check_availability(remote_definition())

        self.assertFalse(availability.available)
        self.assertIn("공개 HTTP Endpoint", availability.message or "")

        with self.assertRaises(LlmProviderUnavailableError) as raised:
            await provider.generate(
                ProviderGenerateRequest.from_prompt("질문"),
                remote_definition(),
            )
        self.assertIn("공개 HTTP Endpoint", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
