"""설정값으로 `ai.rag`의 단일 또는 이중 `EmbeddingProvider`를 만듭니다.

RAG 임베딩을 어떤 provider로 쓸지는 이 파일 한 곳에서만 결정한다 — 팀원이 실제
임베딩 모델을 정하면 `.env`의 `RAG_EMBEDDING_*` 값만 바꾸면 되고,
`document_ingestion_service.py`/`rag_search_service.py` 등 호출부 코드는 손대지
않아도 됩니다. 기본값 `remote_dual`은 Jina v4와 Medical BGE-M3 두 개를
반환하며 OCR 저장과 질문 검색이 같은 Provider 이름을 공유합니다.
"""
from functools import lru_cache

from ai.rag import EmbeddingProvider, HashingEmbeddingProvider, RemoteEmbeddingProvider
from ai.rag.embeddings import SentenceTransformerEmbeddingProvider
from app.core.config import Settings, settings


def build_rag_embedding_provider(config: Settings) -> EmbeddingProvider:
    """설정값 하나로 provider 인스턴스 하나를 만든다. 실제 모델 로드는 아직
    하지 않는다(둘 다 lazy-load) — 여기서 예외가 나는 건 설정 실수(예: provider
    이름 오타, model_name 누락)일 때뿐이다."""
    provider_name = config.rag_embedding_provider

    if provider_name == "remote_dual":
        raise ValueError("remote_dual은 build_rag_embedding_providers()로 생성해야 합니다.")

    if provider_name == "hashing":
        return HashingEmbeddingProvider()

    if provider_name == "sentence_transformer":
        if not config.rag_embedding_model_name:
            raise ValueError(
                "RAG_EMBEDDING_PROVIDER=sentence_transformer인데 "
                "RAG_EMBEDDING_MODEL_NAME이 비어있습니다."
            )
        return SentenceTransformerEmbeddingProvider(
            config.rag_embedding_model_name,
            dimension=config.rag_embedding_dimension,
            truncate_dim=config.rag_embedding_truncate_dim,
            revision=config.rag_embedding_revision,
            trust_remote_code=config.rag_embedding_trust_remote_code,
            query_prompt_name=config.rag_embedding_query_prompt_name,
            document_prompt_name=config.rag_embedding_document_prompt_name,
        )

    raise ValueError(f"알 수 없는 rag_embedding_provider: {provider_name!r}")


def build_rag_embedding_providers(config: Settings) -> list[EmbeddingProvider]:
    """운영용 이중 Provider 또는 개발용 단일 Provider 목록을 만듭니다."""

    if config.rag_embedding_provider != "remote_dual":
        return [build_rag_embedding_provider(config)]

    return build_remote_embedding_providers(config)


def build_remote_embedding_providers(config: Settings) -> list[EmbeddingProvider]:
    """OCR과 RAG가 공유하는 Jina/BGE 원격 Provider 두 개를 만듭니다."""

    common = {
        "base_url": config.embedding_remote_base_url,
        "api_key": config.embedding_api_key,
        "dimension": config.embedding_dimension,
        "timeout_seconds": config.embedding_timeout_seconds,
        "batch_size": config.embedding_batch_size,
    }
    return [
        RemoteEmbeddingProvider(
            model=config.embedding_jina_model,
            name=config.embedding_jina_model,
            **common,
        ),
        RemoteEmbeddingProvider(
            model=config.embedding_bge_model,
            name=config.embedding_bge_model,
            **common,
        ),
    ]


@lru_cache
def get_default_rag_embedding_providers() -> list[EmbeddingProvider]:
    """호출부가 `providers=`를 안 넘겼을 때 쓰는 기본값. `lru_cache`로 프로세스당
    한 번만 만들어서 재사용한다 — sentence-transformers로 바뀐 뒤에도 요청마다
    모델을 새로 인스턴스화하지 않기 위함(모델 자체는 여전히 첫 호출 때 lazy-load)."""
    return build_rag_embedding_providers(settings)
