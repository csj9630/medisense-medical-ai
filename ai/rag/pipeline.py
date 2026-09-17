"""RAG 검색 파이프라인 오케스트레이션 — 로컬 랩과 향후 ai/consultation이 공통으로 쓴다.

흐름: 청크들을 provider마다 각각 dense 랭킹 -> RRF로 결합 -> (옵션) reranker로 정밀화.
provider가 1개면 사실상 단일 dense 검색이고, 2개 이상이면 자연스럽게 앙상블이 된다 —
몇 개를 쓸지는 호출하는 쪽이 정한다(`ai/rag`는 특정 개수나 특정 모델을 가정하지 않음).
"""
from dataclasses import dataclass

import numpy as np

from . import hybrid
from .chunking import Chunk
from .embeddings.base import EmbeddingProvider
from .embeddings.hashing import HashingEmbeddingProvider
from .reranker import rerank as rerank_candidates

# providers를 안 넘긴 호출자(예: local_lab)를 위한 기본값 — 실제 검색 품질을 보장하지
# 않는 자리 채우기용이다. 팀원이 실제 provider를 정하면 호출하는 쪽에서 명시적으로
# providers=[...]를 넘기도록 바꿀 것 (ai/rag/CLAUDE.md 참고).
_DEFAULT_PROVIDERS: list[EmbeddingProvider] = [HashingEmbeddingProvider()]


@dataclass
class RetrievedChunk:
    index: int
    text: str
    score: float
    chunk_id: str | None = None
    document_id: str | None = None
    source: str | None = None
    metadata: dict | None = None


def _rank_by_cosine(query_vector: list[float], chunk_vectors: list[list[float]]) -> list[int]:
    q = np.asarray(query_vector)
    m = np.asarray(chunk_vectors)
    similarities = m @ q  # 임베딩을 normalize해서 만들었으니 내적이 곧 코사인 유사도.
    return np.argsort(-similarities).tolist()


def retrieve(
    chunks: list[Chunk],
    query: str,
    top_k: int = 5,
    use_reranker: bool = False,
    providers: list[EmbeddingProvider] | None = None,
) -> list[RetrievedChunk]:
    if not chunks:
        return []

    providers = providers or _DEFAULT_PROVIDERS
    texts = [c.text for c in chunks]

    ranked_lists: list[list[int]] = []
    for provider in providers:
        chunk_vectors = provider.embed_texts(texts)
        query_vector = provider.embed_query(query)
        ranked_lists.append(_rank_by_cosine(query_vector, chunk_vectors))

    fused = hybrid.reciprocal_rank_fusion(ranked_lists)

    if use_reranker and fused:
        candidate_indices = [i for i, _ in fused[: max(top_k * 3, top_k)]]
        candidate_texts = [texts[i] for i in candidate_indices]
        reranked = rerank_candidates(query, candidate_texts)
        ordered = [(candidate_indices[i], score) for i, score in reranked]
    else:
        ordered = fused

    return [RetrievedChunk(index=i, text=texts[i], score=score) for i, score in ordered[:top_k]]
