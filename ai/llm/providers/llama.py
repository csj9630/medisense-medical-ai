"""Llama-3.2-3B 기반 의료 LoRA 어댑터를 공통 비동기 Provider 계약에 연결합니다.

주의: base model인 `meta-llama/Llama-3.2-3B-Instruct`는 HuggingFace Gated Repo다 —
이 프로젝트의 HF_TOKEN 계정이 Meta 라이선스에 동의하고 저장소 접근 승인을 받아야
실제로 로드된다. **코드 자체는 승인 여부와 무관하게 바로 쓸 수 있게 준비된 상태이고**,
승인 전에는 `generate()`가 `LlmProviderUnavailableError`로 명확히 실패한다
(`ai/llm/engine.py`의 `LoraAdapterEngine._describe_load_error`가 Gated Repo 오류를
구분해서 메시지에 원인을 남긴다) — 조용히 실패하거나 다른 모델로 대체 응답하지 않는다.
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

LLAMA_BASE_MODEL_ID = "meta-llama/Llama-3.2-3B-Instruct"


def _default_engine_factory(hf_token: str | None) -> LoraAdapterEngine:
    return get_lora_engine(LLAMA_BASE_MODEL_ID, hf_token)


class LlamaLlmProvider:
    key = "llama"
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
            return ProviderAvailability(False, "Llama Provider가 비활성화되었습니다.")

        missing = [name for name in self._required_modules if not self._module_exists(name)]
        if missing:
            return ProviderAvailability(
                False,
                "Llama 선택 패키지가 설치되지 않았습니다: " + ", ".join(missing),
            )
        # 패키지 설치 여부만으로는 Gated Repo 접근 승인 여부를 알 수 없다 — 실제
        # 승인 확인은 base model을 내려받는 generate() 시점에야 판별된다(네트워크 호출
        # 없이는 확인 불가하므로 여기서 미리 검사하지 않는다).
        return ProviderAvailability(True)

    async def generate(
        self,
        request: ProviderGenerateRequest,
        model: LlmModelDefinition,
    ) -> ProviderGenerateResult:
        if not self._enabled:
            raise LlmProviderUnavailableError("Llama Provider가 비활성화되었습니다.")

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
            raise LlmUpstreamError("Llama 응답 생성에 실패했습니다.") from exc

        if not answer.strip():
            raise LlmUpstreamError("Llama가 빈 답변을 반환했습니다.")
        return ProviderGenerateResult(answer=answer.strip())

    @staticmethod
    def _module_exists(module_name: str) -> bool:
        try:
            return importlib.util.find_spec(module_name) is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            return False
