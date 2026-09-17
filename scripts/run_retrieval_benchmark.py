"""실제 Neon 코퍼스 + 실제 하이브리드 검색 파이프라인으로 Retrieval Benchmark를
돌린다.

scripts/build_retrieval_benchmark.py가 만든 질의 세트
(scripts/eval_data/retrieval_benchmark_queries.jsonl)를 읽어서, Jina 단독/BGE
단독/RRF 결합(+선택적으로 reranker) 설정으로 각각 실제
`app.services.rag_search_service.search()`를 호출하고 Recall@1/5/10,
Precision@1/5/10, MRR, nDCG@1/5/10을 계산해 비교 리포트를 낸다.

`ai/evaluation`이 아니라 여기(scripts/)에 두는 이유: 실제 검색은 backend/app의
DB 세션 + 실제 원격 임베딩 provider가 필요한데, ai/evaluation/CLAUDE.md가
"backend/app을 import하지 않는다"고 못 박아뒀다(순수 지표 함수만 ai/evaluation
소관). 여긴 그 규칙 밖의 별도 진입점이라 backend/app을 자유롭게 쓴다.
"""
import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

K_VALUES = (1, 5, 10)


def load_queries(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def run_config(db, queries: list[dict], providers, label: str, *, use_reranker: bool = False) -> dict:
    from ai.evaluation.retrieval_metrics import ndcg_at_k, precision_at_k, recall_at_k, reciprocal_rank
    from app.services import rag_search_service

    max_k = max(K_VALUES)
    recalls: dict[int, list[int]] = {k: [] for k in K_VALUES}
    precisions: dict[int, list[float]] = {k: [] for k in K_VALUES}
    ndcgs: dict[int, list[float]] = {k: [] for k in K_VALUES}
    reciprocal_ranks: list[float] = []
    per_source: dict[str, list[int]] = {}
    failed = 0

    started = time.perf_counter()
    for i, q in enumerate(queries, start=1):
        try:
            results = rag_search_service.search(
                db, q["query"], top_k=max_k, providers=providers, use_reranker=use_reranker
            )
        except Exception as exc:  # noqa: BLE001 - 벤치마크 도중 한 질의 실패로 전체가 죽으면 안 됨
            print(f"    [{i}/{len(queries)}] 검색 실패, 스킵: {exc}")
            failed += 1
            continue
        ranked_ids = [r.chunk_id for r in results]
        relevant = q["relevant_chunk_id"]
        for k in K_VALUES:
            recalls[k].append(recall_at_k(ranked_ids, relevant, k))
            precisions[k].append(precision_at_k(ranked_ids, relevant, k))
            ndcgs[k].append(ndcg_at_k(ranked_ids, relevant, k))
        reciprocal_ranks.append(reciprocal_rank(ranked_ids, relevant))

        src = q.get("source", "unknown")
        per_source.setdefault(src, []).append(recall_at_k(ranked_ids, relevant, 5))

    elapsed = time.perf_counter() - started
    n = len(reciprocal_ranks)

    print(f"\n=== {label} ({n}개 질의 성공, {failed}개 실패, {elapsed:.1f}초) ===")
    if n == 0:
        print("  (성공한 질의 없음)")
        return {"label": label, "recall_at_k": {k: 0.0 for k in K_VALUES}, "mrr": 0.0}

    for k in K_VALUES:
        print(f"  Recall@{k}:    {sum(recalls[k]) / n:.3f}")
    for k in K_VALUES:
        print(f"  Precision@{k}: {sum(precisions[k]) / n:.3f}")
    for k in K_VALUES:
        print(f"  nDCG@{k}:      {sum(ndcgs[k]) / n:.3f}")
    print(f"  MRR:           {sum(reciprocal_ranks) / n:.3f}")
    print("  Recall@5 by source:")
    for src, vals in sorted(per_source.items()):
        print(f"    - {src}: {sum(vals) / len(vals):.3f} (n={len(vals)})")

    return {
        "label": label,
        "recall_at_k": {k: sum(v) / n for k, v in recalls.items()},
        "mrr": sum(reciprocal_ranks) / n,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Retrieval Benchmark 실행")
    parser.add_argument(
        "--queries", default=str(PROJECT_ROOT / "scripts" / "eval_data" / "retrieval_benchmark_queries.jsonl")
    )
    parser.add_argument("--limit", type=int, default=None, help="빠른 확인용 - 앞에서부터 N개만")
    parser.add_argument("--reranker", action="store_true", help="RRF+reranker 설정도 같이 돌린다(느림)")
    args = parser.parse_args(argv)

    from app.core.config import settings
    from app.core.database import SessionLocal
    from app.core.rag_embedding import build_remote_embedding_providers

    queries = load_queries(args.queries)
    if args.limit:
        queries = queries[: args.limit]
    print(f"질의 {len(queries)}개로 벤치마크 시작")

    jina, bge = build_remote_embedding_providers(settings)

    db = SessionLocal()
    try:
        results = [
            run_config(db, queries, [jina], "Jina 단독"),
            run_config(db, queries, [bge], "BGE-M3 단독"),
            run_config(db, queries, [jina, bge], "RRF 결합(Jina+BGE)"),
        ]
        if args.reranker:
            results.append(run_config(db, queries, [jina, bge], "RRF+Reranker", use_reranker=True))
    finally:
        db.close()

    print("\n=== 요약 ===")
    header = f"{'설정':<22}{'Recall@1':<10}{'Recall@5':<10}{'Recall@10':<10}{'MRR':<10}"
    print(header)
    for r in results:
        print(
            f"{r['label']:<22}{r['recall_at_k'][1]:<10.3f}{r['recall_at_k'][5]:<10.3f}"
            f"{r['recall_at_k'][10]:<10.3f}{r['mrr']:<10.3f}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
