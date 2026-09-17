"""Model Registry와 Provider 실행을 조율하는 LLM 중심 Service입니다."""

import asyncio
import time

from ai.llm.contracts import (
    LlmExecutionResult,
    LlmModelCatalogEntry,
    LlmModelDefinition,
    LlmProviderUnavailableError,
    ProviderAvailability,
    ProviderGenerateRequest,
)
from ai.llm.registry import ModelRegistry, ProviderRegistry


class LlmApplicationService:
    def __init__(
        self,
        model_registry: ModelRegistry,
        provider_registry: ProviderRegistry,
    ) -> None:
        self.model_registry = model_registry
        self.provider_registry = provider_registry

    def resolve_model(self, model_id: str) -> LlmModelDefinition:
        return self.model_registry.resolve(model_id)

    async def list_models(self) -> list[LlmModelCatalogEntry]:
        """모델을 실제로 로드하지 않고 Provider 가용성을 병렬 확인합니다."""

        return await asyncio.gather(
            *(self._build_catalog_entry(definition) for definition in self.model_registry.list())
        )

    async def _build_catalog_entry(
        self,
        definition: LlmModelDefinition,
    ) -> LlmModelCatalogEntry:
        if not definition.enabled:
            return LlmModelCatalogEntry(
                definition=definition,
                provider=definition.provider_key,
                is_mock=False,
                availability=ProviderAvailability(False, "비활성화된 모델입니다."),
            )

        try:
            provider = self.provider_registry.resolve(definition.provider_key)
            availability = await provider.check_availability(definition)
        except LlmProviderUnavailableError as exc:
            return LlmModelCatalogEntry(
                definition=definition,
                provider=definition.provider_key,
                is_mock=False,
                availability=ProviderAvailability(False, str(exc)),
            )

        return LlmModelCatalogEntry(
            definition=definition,
            provider=provider.key,
            is_mock=provider.is_mock,
            availability=availability,
        )

    async def run(
        self,
        model_id: str,
        request: ProviderGenerateRequest,
    ) -> LlmExecutionResult:
        """모델과 Provider를 결정하고 실행 결과를 공통 계약으로 반환합니다."""

        # 1. 요청 Model ID를 공통 Registry에서 조회합니다.
        definition = self.model_registry.resolve(model_id)
        if not definition.enabled:
            raise LlmProviderUnavailableError("비활성화된 모델입니다.")

        # 2. 모델에 연결된 Provider 구현을 조회합니다.
        provider = self.provider_registry.resolve(definition.provider_key)

        # 3. Provider 호출 결과와 소요 시간을 중심 Service로 다시 반환받습니다.
        started_at = time.perf_counter()
        result = await provider.generate(request, definition)

        # 4. Backend Adapter가 공통으로 사용할 실행 결과를 구성합니다.
        return LlmExecutionResult(
            definition=definition,
            provider=provider.key,
            is_mock=provider.is_mock,
            result=result,
            response_time_seconds=time.perf_counter() - started_at,
        )
