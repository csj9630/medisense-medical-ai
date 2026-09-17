"""Qwen3-4B 기반 의료 LoRA 어댑터를 공통 비동기 Provider 계약에 연결합니다.

`MedGemmaLlmProvider`와 구조는 같지만 base model이 다르므로(Qwen/Qwen3-4B) 별도
`LoraAdapterEngine` 인스턴스(`get_lora_engine`)를 쓴다 — MedGemma의 base model과
같은 GPU 메모리에 중복 로드되지 않게, base model마다 엔진을 하나씩만 유지한다.
"""

import asyncio
import importlib.util
from collections.abc import Callable

from ai.llm.contracts import (
    LlmModelDefinition,
    LlmProviderUnavailableError,
    LlmUpstreamError,
    ProviderAvailability,
    ProviderGenerateRequest,
    ProviderGenerateResult,
)
from ai.llm.engine import LoraAdapterEngine, get_lora_engine

QWEN_BASE_MODEL_ID = "Qwen/Qwen3-4B"


def _default_engine_factory(hf_token: str | None) -> LoraAdapterEngine:
    return get_lora_engine(QWEN_BASE_MODEL_ID, hf_token)


class QwenLlmProvider:
    key = "qwen"
    is_mock = False
    _required_modules = ("torch", "transformers", "peft", "bitsandbytes", "accelerate")

    def __init__(
        self,
        *,
        enabled: bool,
        hf_token: str | None,
        max_concurrency: int = 1,
        engine_factory: Callable[[str | None], LoraAdapterEngine] = _default_engine_factory,
    ) -> None:
        self._enabled = enabled
        self._hf_token = hf_token
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self._engine_factory = engine_factory

    async def check_availability(self, model: LlmModelDefinition) -> ProviderAvailability:
        del model
        if not self._enabled:
            return ProviderAvailability(False, "Qwen Provider가 비활성화되었습니다.")

        missing = [name for name in self._required_modules if not self._module_exists(name)]
        if missing:
            return ProviderAvailability(
                False,
                "Qwen 선택 패키지가 설치되지 않았습니다: " + ", ".join(missing),
            )
        return ProviderAvailability(True)

    async def generate(
        self,
        request: ProviderGenerateRequest,
        model: LlmModelDefinition,
    ) -> ProviderGenerateResult:
        if not self._enabled:
            raise LlmProviderUnavailableError("Qwen Provider가 비활성화되었습니다.")

        messages = [
            {"role": message.role, "content": message.content}
            for message in request.messages
        ]
        generation_overrides = {}
        if request.max_output_tokens is not None:
            generation_overrides["max_new_tokens"] = request.max_output_tokens

        try:
            engine = self._engine_factory(self._hf_token)
            async with self._semaphore:
                answer = await asyncio.to_thread(
                    engine.generate,
                    model.id,
                    model.provider_model,
                    messages,
                    **generation_overrides,
                )
        except (ImportError, RuntimeError) as exc:
            raise LlmProviderUnavailableError(str(exc)) from exc
        except Exception as exc:
            raise LlmUpstreamError("Qwen 응답 생성에 실패했습니다.") from exc

        if not answer.strip():
            raise LlmUpstreamError("Qwen이 빈 답변을 반환했습니다.")
        return ProviderGenerateResult(answer=answer.strip())

    @staticmethod
    def _module_exists(module_name: str) -> bool:
        try:
            return importlib.util.find_spec(module_name) is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            return False
