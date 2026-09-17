"""RAG 검색 정확도를 실제 평가셋으로 측정한다.

`ai/rag/pipeline.retrieve()`를 쿼리마다 호출하면 매번 corpus 전체를 다시 임베딩하게
되어(O(질문 수 × corpus 크기)) 느리다 — 여기서는 corpus 임베딩을 한 번만 계산해두고
재사용한다. 지금은 dense 검색 1개 provider만 평가한다 — 하이브리드(여러 provider
RRF+reranker) 평가는 정확하려면 실제 서비스 pipeline과 동일한 순서로 돌려야 해서 더
무겁다(TODO, ai/evaluation/CLAUDE.md 참고).

**임베딩 모델을 하드코딩하지 않는다** — 팀원이 실제 모델을 정할 때까지
`ai.rag.HashingEmbeddingProvider`(자리 채우기용, 의미 기반 검색 품질 없음)를 기본값으로
쓴다. 실제 모델이 정해지면 `provider=` 인자로 그 provider를 넘기기만 하면 된다.
"""
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from .retrieval_metrics import reciprocal_rank, recall_at_k

if TYPE_CHECKING:
    from ai.rag.embeddings.base import EmbeddingProvider

DEFAULT_K_VALUES = (1, 5, 10)


@dataclass(frozen=True)
class CorpusDoc:
    id: str
    text: str


@dataclass(frozen=True)
class EvalQuery:
    query: str
    relevant_id: str


@dataclass(frozen=True)
class RetrievalEvalResult:
    num_queries: int
    recall_at_k: dict[int, float]
    mrr: float


def evaluate_retrieval(
    corpus: list[CorpusDoc],
    queries: list[EvalQuery],
    *,
    k_values: tuple[int, ...] = DEFAULT_K_VALUES,
    provider: "EmbeddingProvider | None" = None,
) -> RetrievalEvalResult:
    if not corpus or not queries:
        return RetrievalEvalResult(num_queries=0, recall_at_k={k: 0.0 for k in k_values}, mrr=0.0)

    if provider is None:
        from ai.rag.embeddings.hashing import HashingEmbeddingProvider

        provider = HashingEmbeddingProvider()

    corpus_ids = [doc.id for doc in corpus]
    corpus_vectors = np.asarray(provider.embed_texts([doc.text for doc in corpus]))
    query_vectors = np.asarray(provider.embed_texts([q.query for q in queries]))

    # normalize_embeddings=True로 뽑은 벡터라 내적이 곧 코사인 유사도.
    similarity_matrix = query_vectors @ corpus_vectors.T

    recalls: dict[int, list[int]] = {k: [] for k in k_values}
    reciprocal_ranks: list[float] = []

    for row, eval_query in zip(similarity_matrix, queries, strict=True):
        ranked_idx = np.argsort(-row)
        ranked_ids = [corpus_ids[i] for i in ranked_idx]
        for k in k_values:
            recalls[k].append(recall_at_k(ranked_ids, eval_query.relevant_id, k))
        reciprocal_ranks.append(reciprocal_rank(ranked_ids, eval_query.relevant_id))

    return RetrievalEvalResult(
        num_queries=len(queries),
        recall_at_k={k: sum(v) / len(v) for k, v in recalls.items()},
        mrr=sum(reciprocal_ranks) / len(reciprocal_ranks),
    )


def load_eval_dataset(corpus_path: str, queries_path: str) -> tuple[list[CorpusDoc], list[EvalQuery]]:
    """`scripts/eval_data/*.jsonl` 형식({"id","text"} / {"query","relevant_id"})을 읽는다."""
    import json

    with open(corpus_path, encoding="utf-8") as f:
        corpus = [CorpusDoc(id=row["id"], text=row["text"]) for row in (json.loads(line) for line in f) if row.get("text")]

    with open(queries_path, encoding="utf-8") as f:
        queries = [
            EvalQuery(query=row["query"], relevant_id=row["relevant_id"])
            for row in (json.loads(line) for line in f)
            if row.get("query") and row.get("relevant_id")
        ]

    return corpus, queries
