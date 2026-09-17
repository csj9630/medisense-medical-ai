"""Admin LLM API와 공통 LLM Runtime 사이의 Facade입니다."""

import asyncio
import logging

from app.schemas.admin import (
    LlmCompareRequest,
    LlmModelDefinitionResponse,
    LlmModelResponse,
    LlmRunRequest,
    LlmRunResponse,
)
from ai.llm import (
    LlmExecutionResult,
    LlmServiceError,
    ModelRegistry,
    ProviderGenerateRequest,
)
from app.services.llm_runtime import (
    create_llm_application,
    create_model_registry,
    llm_application,
)

logger = logging.getLogger(__name__)


def create_admin_model_registry() -> ModelRegistry:
    """기존 호출부를 위한 호환 별칭입니다. 신규 코드는 create_model_registry()를 사용합니다."""

    return create_model_registry()


async def list_models() -> list[LlmModelDefinitionResponse]:
    entries = await llm_application.list_models()
    return [
        LlmModelDefinitionResponse(
            id=entry.definition.id,
            label=entry.definition.label,
            family=entry.definition.family,
            trainingStage=entry.definition.training_stage,
            description=entry.definition.description,
            group=entry.definition.group,
            provider=entry.provider,
            providerModel=entry.definition.provider_model,
            enabled=entry.definition.enabled,
            available=entry.availability.available,
            availabilityMessage=entry.availability.message,
            isMock=entry.is_mock,
        )
        for entry in entries
    ]


async def run_model(request: LlmRunRequest) -> LlmRunResponse:
    execution = await llm_application.run(
        request.model_id,
        ProviderGenerateRequest.from_prompt(
            request.prompt.strip(),
            document_name=request.joined_document_names(),
        ),
    )
    logger.info(
        "[AdminLLM] completed: model=%s provider=%s elapsed=%.2fs mock=%s",
        execution.definition.id,
        execution.provider,
        execution.response_time_seconds,
        execution.is_mock,
    )
    return _to_run_response(execution)


def _to_run_response(execution: LlmExecutionResult) -> LlmRunResponse:
    result = execution.result
    return LlmRunResponse(
        modelId=execution.definition.id,
        provider=execution.provider,
        providerModel=execution.definition.provider_model,
        answer=result.answer,
        responseTimeSeconds=execution.response_time_seconds,
        inputTokens=result.input_tokens,
        outputTokens=result.output_tokens,
        totalTokens=result.total_tokens,
        finishReason=result.finish_reason,
        isMock=execution.is_mock,
    )


async def compare_models(request: LlmCompareRequest) -> list[LlmModelResponse]:
    """기존 비교 API를 같은 Provider 실행 경계로 유지합니다."""

    for model_id in request.model_ids:
        llm_application.resolve_model(model_id)
    results = await asyncio.gather(
        *(
            llm_application.run(
                model_id,
                ProviderGenerateRequest.from_prompt(
                    request.prompt.strip(),
                    document_name=request.joined_document_names(),
                ),
            )
            for model_id in request.model_ids
        ),
        return_exceptions=True,
    )
    response: list[LlmModelResponse] = []
    for model_id, result in zip(request.model_ids, results, strict=True):
        if isinstance(result, LlmServiceError):
            response.append(
                LlmModelResponse(
                    modelId=model_id,
                    status="error",
                    error=str(result),
                    responseTimeSeconds=0,
                    inputTokens=None,
                    outputTokens=None,
                    chunkSize=request.chunk_size,
                    overlap=request.overlap,
                )
            )
            continue
        if isinstance(result, BaseException):
            raise result
        response.append(
            LlmModelResponse(
                modelId=model_id,
                status="success",
                answer=result.result.answer,
                responseTimeSeconds=result.response_time_seconds,
                inputTokens=result.result.input_tokens,
                outputTokens=result.result.output_tokens,
                chunkSize=request.chunk_size,
                overlap=request.overlap,
            )
        )
    return response
