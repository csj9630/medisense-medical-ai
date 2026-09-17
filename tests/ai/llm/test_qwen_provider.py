import asyncio
import threading
import time
import unittest

from ai.llm import LlmMessage, LlmProviderUnavailableError, ProviderGenerateRequest
from ai.llm.providers.qwen import QwenLlmProvider
from tests.ai.llm.helpers import model_definition


class FakeEngine:
    """LoraAdapterEngine.generate(adapter_name, adapter_repo, messages, **kwargs) 계약을
    흉내낸다 — MedGemmaEngine과 달리 어댑터 repo를 인자로 직접 받는다."""

    def __init__(self, *, error: Exception | None = None, delay: float = 0.0) -> None:
        self.error = error
        self.delay = delay
        self.calls: list[tuple[str, str, list[dict[str, str]], int]] = []
        self.active = 0
        self.max_active = 0
        self._counter_lock = threading.Lock()

    def generate(self, adapter_name, adapter_repo, messages, **kwargs):
        del kwargs
        with self._counter_lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            self.calls.append((adapter_name, adapter_repo, messages, threading.get_ident()))
            if self.delay:
                time.sleep(self.delay)
            if self.error:
                raise self.error
            return "Qwen 응답"
        finally:
            with self._counter_lock:
                self.active -= 1


def qwen_definition():
    return model_definition(
        model_id="qwen-medical",
        provider_key="qwen",
        provider_model="csj9630/qwen3-4b-medical-qlora",
        group="other",
    )


class QwenProviderTest(unittest.IsolatedAsyncioTestCase):
    async def test_generate_passes_model_id_and_provider_model_to_engine(self) -> None:
        engine = FakeEngine()
        provider = QwenLlmProvider(
            enabled=True,
            hf_token=None,
            engine_factory=lambda token: engine,  # type: ignore[arg-type]
        )
        request = ProviderGenerateRequest(messages=(LlmMessage(role="user", content="질문"),))
        event_loop_thread = threading.get_ident()

        result = await provider.generate(request, qwen_definition())

        self.assertEqual(result.answer, "Qwen 응답")
        adapter_name, adapter_repo, messages, call_thread = engine.calls[0]
        self.assertEqual(adapter_name, "qwen-medical")
        self.assertEqual(adapter_repo, "csj9630/qwen3-4b-medical-qlora")
        self.assertEqual([m["role"] for m in messages], ["user"])
        self.assertNotEqual(call_thread, event_loop_thread)

    async def test_max_concurrency_serializes_engine_execution(self) -> None:
        engine = FakeEngine(delay=0.03)
        provider = QwenLlmProvider(
            enabled=True,
            hf_token=None,
            max_concurrency=1,
            engine_factory=lambda token: engine,  # type: ignore[arg-type]
        )
        request = ProviderGenerateRequest.from_prompt("질문")

        await asyncio.gather(
            provider.generate(request, qwen_definition()),
            provider.generate(request, qwen_definition()),
        )

        self.assertEqual(engine.max_active, 1)

    async def test_runtime_error_is_mapped_to_unavailable(self) -> None:
        engine = FakeEngine(error=RuntimeError("GPU가 없습니다."))
        provider = QwenLlmProvider(
            enabled=True,
            hf_token=None,
            engine_factory=lambda token: engine,  # type: ignore[arg-type]
        )

        with self.assertRaises(LlmProviderUnavailableError) as raised:
            await provider.generate(ProviderGenerateRequest.from_prompt("질문"), qwen_definition())

        self.assertIn("GPU", str(raised.exception))

    async def test_disabled_provider_raises_without_touching_engine(self) -> None:
        provider = QwenLlmProvider(enabled=False, hf_token=None)

        with self.assertRaises(LlmProviderUnavailableError):
            await provider.generate(ProviderGenerateRequest.from_prompt("질문"), qwen_definition())

    async def test_availability_does_not_create_or_load_engine(self) -> None:
        factory_called = False

        def factory(token):
            nonlocal factory_called
            factory_called = True
            return FakeEngine()

        provider = QwenLlmProvider(enabled=True, hf_token=None, engine_factory=factory)  # type: ignore[arg-type]
        from unittest.mock import patch

        with patch.object(provider, "_module_exists", return_value=True):
            availability = await provider.check_availability(qwen_definition())

        self.assertTrue(availability.available)
        self.assertFalse(factory_called)


if __name__ == "__main__":
    unittest.main()
