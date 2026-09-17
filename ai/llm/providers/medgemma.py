"""동기식 MedGemma Engine을 공통 비동기 Provider 계약에 연결합니다."""

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
    UnknownLlmModelError,
)
from ai.llm.engine import MedGemmaEngine, get_engine


class MedGemmaLlmProvider:
    key = "medgemma"
    is_mock = False
    _required_modules = ("torch", "transformers", "peft", "bitsandbytes", "accelerate")

    def __init__(
        self,
        *,
        enabled: bool,
        hf_token: str | None,
        max_concurrency: int = 1,
        engine_factory: Callable[[str | None], MedGemmaEngine] = get_engine,
    ) -> None:
        self._enabled = enabled
        self._hf_token = hf_token
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self._engine_factory = engine_factory

    async def check_availability(self, model: LlmModelDefinition) -> ProviderAvailability:
        del model
        if not self._enabled:
            return ProviderAvailability(False, "MedGemma Provider가 비활성화되었습니다.")

        missing = [name for name in self._required_modules if not self._module_exists(name)]
        if missing:
            return ProviderAvailability(
                False,
                "MedGemma 선택 패키지가 설치되지 않았습니다: " + ", ".join(missing),
            )
        return ProviderAvailability(True)

    async def generate(
        self,
        request: ProviderGenerateRequest,
        model: LlmModelDefinition,
    ) -> ProviderGenerateResult:
        if not self._enabled:
            raise LlmProviderUnavailableError("MedGemma Provider가 비활성화되었습니다.")

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
                    messages,
                    **generation_overrides,
                )
        except KeyError as exc:
            raise UnknownLlmModelError(f"지원하지 않는 모델입니다: {model.id}") from exc
        except (ImportError, RuntimeError) as exc:
            raise LlmProviderUnavailableError(str(exc)) from exc
        except Exception as exc:
            raise LlmUpstreamError("MedGemma 응답 생성에 실패했습니다.") from exc

        if not answer.strip():
            raise LlmUpstreamError("MedGemma가 빈 답변을 반환했습니다.")
        return ProviderGenerateResult(answer=answer.strip())

    @staticmethod
    def _module_exists(module_name: str) -> bool:
        try:
            return importlib.util.find_spec(module_name) is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            return False
