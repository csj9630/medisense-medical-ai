"""텍스트를 청킹→임베딩→document_chunks/chunk_embeddings 저장까지 처리한다.

ai/rag는 순수 로직(청킹/임베딩)만 담당하고, DB 저장은 여기 backend 쪽 책임이다
(루트 CLAUDE.md 원칙). 임베딩 provider는 이 함수를 호출하는 쪽이 넘긴다 — 팀원이
실제 모델을 정할 때까지는 기본값(해싱 placeholder)을 쓰고, 나중엔 실제 provider
인스턴스만 바꿔서 넘기면 된다.
"""
from uuid import UUID

from ai.rag import EmbeddingProvider, chunk_text
from app.core.logging import get_logger
from app.core.rag_embedding import get_default_rag_embedding_providers
from app.repositories.document_chunk import DocumentChunkRepository

logger = get_logger("services.document_ingestion")


def ingest_document(
    repo: DocumentChunkRepository,
    document_id: UUID,
    text: str,
    *,
    providers: list[EmbeddingProvider] | None = None,
    replace_existing: bool = True,
    metadata: dict | None = None,
) -> int:
    """document_id(= vector_db.admin_documents.id)에 딸린 청크를 새로 만들어 저장한다.
    반환값: 실제로 저장된 청크 개수(쓰레기 필터링 후 0개면 아무 것도 안 하고 0 반환).
    metadata는 문서 전체 청크에 동일하게 적용된다(RAG 데이터셋 ingestion에서 출처/
    진료과/신뢰도 등을 그대로 통과시킨다 — 생략하면 기존 호출부와 동일하게 NULL)."""
    providers = providers or get_default_rag_embedding_providers()

    chunks = chunk_text(text)
    if not chunks:
        logger.warning("ingest_document: 청킹 결과가 비어있음 document_id=%s", document_id)
        return 0

    if replace_existing:
        repo.delete_by_document(document_id)

    saved_chunks = repo.create_chunks(
        document_id,
        [{"chunk_index": c.index, "chunk_text": c.text} for c in chunks],
        metadata=metadata,
    )

    texts = [c.chunk_text for c in saved_chunks]
    for provider in providers:
        vectors = provider.embed_texts(texts)
        for chunk, vector in zip(saved_chunks, vectors, strict=True):
            repo.add_embeddings(chunk.id, provider.name, provider.dimension, vector)

    logger.info(
        "ingest_document: %d개 청크 저장 document_id=%s providers=%s",
        len(saved_chunks), document_id, [p.name for p in providers],
    )
    return len(saved_chunks)
