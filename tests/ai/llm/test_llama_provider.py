import asyncio
import threading
import unittest
from unittest.mock import patch

from ai.llm import LlmMessage, LlmProviderUnavailableError, ProviderGenerateRequest
from ai.llm.providers.llama import LlamaLlmProvider
from tests.ai.llm.helpers import model_definition


class FakeEngine:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, str, list[dict[str, str]]]] = []

    def generate(self, adapter_name, adapter_repo, messages, **kwargs):
        del kwargs
        self.calls.append((adapter_name, adapter_repo, messages))
        if self.error:
            raise self.error
        return "Llama 응답"


def llama_definition():
    return model_definition(
        model_id="llama-medical",
        provider_key="llama",
        provider_model="csj9630/llama32-3b-medical-qlora",
        group="other",
    )


class LlamaProviderTest(unittest.IsolatedAsyncioTestCase):
    async def test_generate_passes_model_id_and_provider_model_to_engine(self) -> None:
        engine = FakeEngine()
        provider = LlamaLlmProvider(
            enabled=True,
            hf_token=None,
            engine_factory=lambda token: engine,  # type: ignore[arg-type]
        )
        request = ProviderGenerateRequest(messages=(LlmMessage(role="user", content="질문"),))

        result = await provider.generate(request, llama_definition())

        self.assertEqual(result.answer, "Llama 응답")
        adapter_name, adapter_repo, messages = engine.calls[0]
        self.assertEqual(adapter_name, "llama-medical")
        self.assertEqual(adapter_repo, "csj9630/llama32-3b-medical-qlora")
        self.assertEqual([m["role"] for m in messages], ["user"])

    async def test_gated_repo_style_runtime_error_is_mapped_to_unavailable_not_swallowed(self) -> None:
        # 접근 승인 전 base model 로드 실패를 흉내낸다(engine.py의
        # LoraAdapterEngine._describe_load_error가 실제로 만드는 메시지 형태) — 조용히
        # 성공한 것처럼 처리되지 않고 명확한 오류로 올라와야 한다.
        engine = FakeEngine(
            error=RuntimeError(
                "'meta-llama/Llama-3.2-3B-Instruct'는 HuggingFace Gated Repo입니다 — "
                "라이선스에 동의하고 접근 승인을 받은 계정의 HF_TOKEN이 필요합니다."
            )
        )
        provider = LlamaLlmProvider(
            enabled=True,
            hf_token=None,
            engine_factory=lambda token: engine,  # type: ignore[arg-type]
        )

        with self.assertRaises(LlmProviderUnavailableError) as raised:
            await provider.generate(ProviderGenerateRequest.from_prompt("질문"), llama_definition())

        self.assertIn("Gated Repo", str(raised.exception))

    async def test_max_concurrency_serializes_engine_execution(self) -> None:
        import time

        class SlowEngine(FakeEngine):
            def __init__(self):
                super().__init__()
                self.active = 0
                self.max_active = 0
                self._lock = threading.Lock()

            def generate(self, adapter_name, adapter_repo, messages, **kwargs):
                with self._lock:
                    self.active += 1
                    self.max_active = max(self.max_active, self.active)
                try:
                    time.sleep(0.03)
                    return super().generate(adapter_name, adapter_repo, messages, **kwargs)
                finally:
                    with self._lock:
                        self.active -= 1

        engine = SlowEngine()
        provider = LlamaLlmProvider(
            enabled=True,
            hf_token=None,
            max_concurrency=1,
            engine_factory=lambda token: engine,  # type: ignore[arg-type]
        )
        request = ProviderGenerateRequest.from_prompt("질문")

        await asyncio.gather(
            provider.generate(request, llama_definition()),
            provider.generate(request, llama_definition()),
        )

        self.assertEqual(engine.max_active, 1)

    async def test_disabled_provider_raises_without_touching_engine(self) -> None:
        provider = LlamaLlmProvider(enabled=False, hf_token=None)

        with self.assertRaises(LlmProviderUnavailableError):
            await provider.generate(ProviderGenerateRequest.from_prompt("질문"), llama_definition())

    async def test_availability_does_not_create_or_load_engine(self) -> None:
        factory_called = False

        def factory(token):
            nonlocal factory_called
            factory_called = True
            return FakeEngine()

        provider = LlamaLlmProvider(enabled=True, hf_token=None, engine_factory=factory)  # type: ignore[arg-type]
        with patch.object(provider, "_module_exists", return_value=True):
            availability = await provider.check_availability(llama_definition())

        # 패키지 설치 여부만 확인하고 Gated Repo 접근 승인 여부는 알 수 없다 —
        # available=True라도 실제 generate()는 승인 전까지 계속 실패할 수 있다.
        self.assertTrue(availability.available)
        self.assertFalse(factory_called)


if __name__ == "__main__":
    unittest.main()
