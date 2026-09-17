import asyncio
import threading
import time
import unittest
from unittest.mock import patch

from ai.llm import LlmMessage, LlmProviderUnavailableError, ProviderGenerateRequest
from ai.llm.providers.medgemma import MedGemmaLlmProvider
from tests.ai.llm.helpers import model_definition


class FakeEngine:
    def __init__(self, *, error: Exception | None = None, delay: float = 0.0) -> None:
        self.error = error
        self.delay = delay
        self.calls: list[tuple[str, list[dict[str, str]], int]] = []
        self.active = 0
        self.max_active = 0
        self._counter_lock = threading.Lock()

    def generate(self, model_id, messages, **kwargs):
        del kwargs
        with self._counter_lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            self.calls.append((model_id, messages, threading.get_ident()))
            if self.delay:
                time.sleep(self.delay)
            if self.error:
                raise self.error
            return "MedGemma 응답"
        finally:
            with self._counter_lock:
                self.active -= 1


def medgemma_definition():
    return model_definition(
        model_id="medgemma-main",
        provider_key="medgemma",
        provider_model="adapter/repo",
        group="other",
    )


class MedGemmaProviderTest(unittest.IsolatedAsyncioTestCase):
    async def test_generation_runs_outside_event_loop_and_keeps_messages(self) -> None:
        engine = FakeEngine()
        provider = MedGemmaLlmProvider(
            enabled=True,
            hf_token=None,
            engine_factory=lambda token: engine,  # type: ignore[arg-type]
        )
        request = ProviderGenerateRequest(
            messages=(
                LlmMessage(role="user", content="질문"),
                LlmMessage(role="assistant", content="이전 답변"),
                LlmMessage(role="user", content="후속 질문"),
            )
        )
        event_loop_thread = threading.get_ident()

        result = await provider.generate(request, medgemma_definition())

        self.assertEqual(result.answer, "MedGemma 응답")
        self.assertNotEqual(engine.calls[0][2], event_loop_thread)
        self.assertEqual(
            [message["role"] for message in engine.calls[0][1]],
            ["user", "assistant", "user"],
        )

    async def test_max_concurrency_serializes_engine_execution(self) -> None:
        engine = FakeEngine(delay=0.03)
        provider = MedGemmaLlmProvider(
            enabled=True,
            hf_token=None,
            max_concurrency=1,
            engine_factory=lambda token: engine,  # type: ignore[arg-type]
        )
        request = ProviderGenerateRequest.from_prompt("질문")

        await asyncio.gather(
            provider.generate(request, medgemma_definition()),
            provider.generate(request, medgemma_definition()),
        )

        self.assertEqual(engine.max_active, 1)

    async def test_runtime_error_is_mapped_to_unavailable(self) -> None:
        engine = FakeEngine(error=RuntimeError("GPU가 없습니다."))
        provider = MedGemmaLlmProvider(
            enabled=True,
            hf_token=None,
            engine_factory=lambda token: engine,  # type: ignore[arg-type]
        )

        with self.assertRaises(LlmProviderUnavailableError) as raised:
            await provider.generate(
                ProviderGenerateRequest.from_prompt("질문"),
                medgemma_definition(),
            )

        self.assertIn("GPU", str(raised.exception))

    async def test_availability_does_not_create_or_load_engine(self) -> None:
        factory_called = False

        def factory(token):
            nonlocal factory_called
            factory_called = True
            return FakeEngine()

        provider = MedGemmaLlmProvider(
            enabled=True,
            hf_token=None,
            engine_factory=factory,  # type: ignore[arg-type]
        )
        with patch.object(provider, "_module_exists", return_value=True):
            availability = await provider.check_availability(medgemma_definition())

        self.assertTrue(availability.available)
        self.assertFalse(factory_called)


if __name__ == "__main__":
    unittest.main()
