"""하이브리드 검색 비교 — RRF만 쓴 결과 vs RRF 결과를 reranker로 다시 정렬한 결과.

ai/rag에 이미 있는 걸 그대로 씀: embed_texts/embed_query(의미기반) + keyword_search(Kiwi+
Tantivy, 키워드기반) + reciprocal_rank_fusion(RRF) + reranker.rerank(cross-encoder).

사용법:
    python scripts/compare_hybrid_retrieval.py --limit 150
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np

from ai.evaluation import recall_at_k, reciprocal_rank
from ai.rag import chunk_text  # noqa: F401  (미사용이지만 ai.rag import 확인용)
from ai.rag.hybrid import reciprocal_rank_fusion
from ai.rag.keyword_search import search as keyword_search
from ai.rag.reranker import rerank

EVAL_DIR = Path(__file__).parent / "eval_data"
K_VALUES = [1, 5, 10]
RRF_CANDIDATES = 20  # reranker에 넘길 RRF 상위 후보 개수


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def evaluate(corpus: list[dict], queries: list[dict], embed_model_name: str) -> None:
    from sentence_transformers import SentenceTransformer

    corpus_ids = [row["id"] for row in corpus]
    corpus_texts = [row["text"] for row in corpus]

    print(f"임베딩 모델: {embed_model_name} (의미기반 랭킹용)")
    model = SentenceTransformer(embed_model_name)
    t0 = time.time()
    corpus_vectors = np.asarray(model.encode(corpus_texts, normalize_embeddings=True, show_progress_bar=False))
    query_vectors = np.asarray(
        model.encode([q["query"] for q in queries], normalize_embeddings=True, show_progress_bar=False)
    )
    print(f"임베딩 완료 ({time.time() - t0:.1f}초)\n")

    rrf_recalls = {k: [] for k in K_VALUES}
    rrf_rr = []
    reranked_recalls = {k: [] for k in K_VALUES}
    reranked_rr = []

    sims = query_vectors @ corpus_vectors.T

    for row_idx, q in enumerate(queries):
        dense_ranked_idx = np.argsort(-sims[row_idx]).tolist()
        keyword_hits = keyword_search(corpus_texts, q["query"], top_k=len(corpus_texts))
        keyword_ranked_idx = [i for i, _score in keyword_hits]

        fused = reciprocal_rank_fusion([dense_ranked_idx, keyword_ranked_idx])
        rrf_ranked_ids = [corpus_ids[i] for i, _score in fused]

        for k in K_VALUES:
            rrf_recalls[k].append(recall_at_k(rrf_ranked_ids, q["relevant_id"], k))
        rrf_rr.append(reciprocal_rank(rrf_ranked_ids, q["relevant_id"]))

        # RRF 상위 후보만 reranker로 다시 정렬
        candidate_indices = [i for i, _score in fused[:RRF_CANDIDATES]]
        candidate_texts = [corpus_texts[i] for i in candidate_indices]
        reranked = rerank(q["query"], candidate_texts)
        reranked_ids = [corpus_ids[candidate_indices[i]] for i, _score in reranked]

        for k in K_VALUES:
            reranked_recalls[k].append(recall_at_k(reranked_ids, q["relevant_id"], k))
        reranked_rr.append(reciprocal_rank(reranked_ids, q["relevant_id"]))

        if (row_idx + 1) % 25 == 0:
            print(f"  {row_idx + 1}/{len(queries)}개 처리")

    print("\n=== 결과 ===")
    print(
        "RRF만        | mrr:",
        round(float(np.mean(rrf_rr)), 4),
        {f"recall@{k}": round(float(np.mean(v)), 4) for k, v in rrf_recalls.items()},
    )
    print(
        "RRF+Reranker | mrr:",
        round(float(np.mean(reranked_rr)), 4),
        {f"recall@{k}": round(float(np.mean(v)), 4) for k, v in reranked_recalls.items()},
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=150, help="쿼리 개수 제한 (reranker가 느려서 기본 150)")
    parser.add_argument(
        "--embed-model",
        type=str,
        default="jhgan/ko-sroberta-multitask",
        help="의미기반 랭킹에 쓸 임베딩 모델 (빠른 비교용 기본값)",
    )
    args = parser.parse_args()

    corpus = load_jsonl(EVAL_DIR / "embedding_corpus.jsonl")
    queries = load_jsonl(EVAL_DIR / "embedding_queries.jsonl")
    if args.limit:
        queries = queries[: args.limit]

    print(f"코퍼스 {len(corpus)}개, 쿼리 {len(queries)}개로 평가\n")
    evaluate(corpus, queries, args.embed_model)


if __name__ == "__main__":
    main()
