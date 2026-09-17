import json
import unittest

import httpx

from ai.llm import LlmMessage, ProviderGenerateRequest
from ai.llm.providers.ollama import OllamaLlmProvider
from tests.ai.llm.helpers import model_definition


class OllamaProviderTest(unittest.IsolatedAsyncioTestCase):
    async def test_chat_messages_and_real_token_counts_are_mapped(self) -> None:
        captured: dict[str, object] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/tags":
                return httpx.Response(200, json={"models": [{"name": "gemma3:1b"}]})
            captured.update(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "message": {"role": "assistant", "content": "실제 응답"},
                    "prompt_eval_count": 12,
                    "eval_count": 34,
                    "done_reason": "stop",
                },
            )

        provider = OllamaLlmProvider(
            enabled=True,
            base_url="http://127.0.0.1:11434",
            timeout_seconds=10,
            max_concurrency=1,
            transport=httpx.MockTransport(handler),
        )
        request = ProviderGenerateRequest(
            messages=(
                LlmMessage(role="system", content="근거만 답변"),
                LlmMessage(role="user", content="첫 질문"),
                LlmMessage(role="assistant", content="첫 답변"),
                LlmMessage(role="user", content="후속 질문"),
            )
        )

        availability = await provider.check_availability(model_definition())
        result = await provider.generate(request, model_definition())

        self.assertTrue(availability.available)
        self.assertEqual(captured["model"], "gemma3:1b")
        self.assertFalse(captured["stream"])
        self.assertEqual(
            [item["role"] for item in captured["messages"]],  # type: ignore[index]
            ["system", "user", "assistant", "user"],
        )
        self.assertEqual(result.answer, "실제 응답")
        self.assertEqual((result.input_tokens, result.output_tokens, result.total_tokens), (12, 34, 46))

    async def test_missing_model_is_unavailable(self) -> None:
        provider = OllamaLlmProvider(
            enabled=True,
            base_url="http://127.0.0.1:11434",
            timeout_seconds=10,
            max_concurrency=1,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"models": []})
            ),
        )

        availability = await provider.check_availability(model_definition())

        self.assertFalse(availability.available)
        self.assertIn("설치되지", availability.message or "")


if __name__ == "__main__":
    unittest.main()
