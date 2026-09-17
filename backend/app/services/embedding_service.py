"""OCR Chunk를 Jina v4·Medical BGE-M3 이중 Vector로 변환합니다."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol

from ai.rag import EmbeddingProvider, RemoteEmbeddingError
from app.core.config import Settings, settings
from app.core.rag_embedding import build_remote_embedding_providers

logger = logging.getLogger(__name__)


class EmbeddingServiceError(Exception):
    """Embedding 단계에서 처리 가능한 오류의 공통 부모입니다."""


class EmbeddingUnavailableError(EmbeddingServiceError):
    """원격 설정이 없어 Embedding을 사용할 수 없을 때 발생합니다."""


class EmbeddingGenerationError(EmbeddingServiceError):
    """원격 호출이 실패하거나 잘못된 응답을 반환할 때 발생합니다."""


class EmbeddingValidationError(EmbeddingServiceError):
    """Chunk 또는 Vector가 DB 저장 계약을 만족하지 않을 때 발생합니다."""


@dataclass(frozen=True)
class EmbeddingBatch:
    """Provider 이름별로 입력 순서를 유지한 Vector를 보관합니다."""

    vectors_by_provider: dict[str, list[list[float]]]

    @property
    def count(self) -> int:
        first = next(iter(self.vectors_by_provider.values()), [])
        return len(first)


class EmbeddingService(Protocol):
    provider: str
    model: str
    models: tuple[str, ...]
    dimension: int

    async def embed_chunks(self, chunks: list[str]) -> EmbeddingBatch: ...


class RemoteDualEmbeddingService:
    """두 원격 Provider를 별도 Thread에서 동시에 호출합니다."""

    provider = "remote-dual"

    def __init__(self, providers: list[EmbeddingProvider]) -> None:
        if len(providers) != 2:
            raise EmbeddingUnavailableError("Jina/BGE Embedding Provider가 두 개 필요합니다.")
        self.providers = tuple(providers)
        self.models = tuple(provider.name for provider in providers)
        self.model = " + ".join(self.models)
        dimensions = {provider.dimension for provider in providers}
        if dimensions != {1024}:
            raise EmbeddingValidationError("두 Embedding Provider는 모두 1024차원이어야 합니다.")
        self.dimension = 1024

    async def embed_chunks(self, chunks: list[str]) -> EmbeddingBatch:
        if not chunks or any(not chunk.strip() for chunk in chunks):
            raise EmbeddingValidationError("빈 OCR Chunk는 Embedding할 수 없습니다.")

        logger.info(
            "[EMBEDDING] remote dual start: chunks=%d models=%s",
            len(chunks),
            self.models,
        )
        try:
            results = await asyncio.gather(
                *(
                    asyncio.to_thread(provider.embed_texts, chunks)
                    for provider in self.providers
                )
            )
        except RemoteEmbeddingError as exc:
            message = str(exc)
            if "EMBEDDING_REMOTE_BASE_URL" in message:
                raise EmbeddingUnavailableError(message) from exc
            raise EmbeddingGenerationError(message) from exc
        except Exception as exc:
            logger.warning(
                "[EMBEDDING] remote dual failure: error_type=%s",
                type(exc).__name__,
            )
            raise EmbeddingGenerationError("Embedding 생성에 실패했습니다.") from exc

        vectors_by_provider = dict(zip(self.models, results, strict=True))
        self._validate_result(vectors_by_provider, expected_count=len(chunks))
        logger.info("[EMBEDDING] remote dual complete: chunks=%d", len(chunks))
        return EmbeddingBatch(vectors_by_provider=vectors_by_provider)

    def _validate_result(
        self,
        vectors_by_provider: dict[str, list[list[float]]],
        *,
        expected_count: int,
    ) -> None:
        for provider_name, vectors in vectors_by_provider.items():
            if len(vectors) != expected_count:
                raise EmbeddingValidationError(
                    f"{provider_name} Vector 개수가 OCR Chunk 개수와 다릅니다."
                )
            for index, vector in enumerate(vectors):
                if len(vector) != self.dimension:
                    raise EmbeddingValidationError(
                        f"{provider_name} Chunk {index}의 Vector는 "
                        f"{self.dimension}차원이어야 합니다."
                    )


def create_embedding_service(app_settings: Settings = settings) -> EmbeddingService:
    """Backend 설정으로 OCR·RAG 공통 이중 Provider를 만듭니다."""

    try:
        providers = build_remote_embedding_providers(app_settings)
    except (TypeError, ValueError) as exc:
        raise EmbeddingUnavailableError(str(exc)) from exc
    return RemoteDualEmbeddingService(providers)


embedding_service = create_embedding_service()
