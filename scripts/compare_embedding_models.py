"""임베딩 모델 비교 — scripts/eval_data/의 쿼리·코퍼스로 Recall@k, MRR 계산.

먼저 scripts/build_embedding_eval_set.py로 평가셋을 만들어야 한다.
GPU 없이 CPU로 돈다.

일부 모델(mejurix/medical-legal-embedder 등)은 sentence-transformers 포맷이 아니라
일반 transformers 모델 + CLS 토큰 풀링 방식이라, POOLING_OVERRIDES에 등록해서 따로 처리한다.

사용법:
    python scripts/compare_embedding_models.py
    python scripts/compare_embedding_models.py --models "모델A,모델B"
    python scripts/compare_embedding_models.py --limit 200   # 빠른 사전 확인용 (전체 대신 일부만)
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np

from ai.evaluation import recall_at_k, reciprocal_rank

EVAL_DIR = Path(__file__).parent / "eval_data"

# 기본 비교 대상: 현재 프로덕션(ai/rag) 모델 vs 사용자가 요청한 의료 도메인 특화 후보.
DEFAULT_MODELS = [
    "dragonkue/snowflake-arctic-embed-l-v2.0-ko",  # 현재 프로덕션(ai/rag) 기본값
    "mejurix/medical-legal-embedder",  # 비교 후보 — ClinicalBERT 기반, CLS 풀링
]

# sentence-transformers 포맷이 아니라 CLS 토큰 풀링으로 직접 인코딩해야 하는 모델들.
POOLING_OVERRIDES = {"mejurix/medical-legal-embedder"}

K_VALUES = [1, 5, 10]
BATCH_SIZE = 16


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def encode_sentence_transformers(model_name: str, texts: list[str]) -> np.ndarray:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)
    return np.asarray(model.encode(texts, normalize_embeddings=True, show_progress_bar=False, batch_size=BATCH_SIZE))


def encode_cls_pooling(model_name: str, texts: list[str]) -> np.ndarray:
    """sentence-transformers를 안 쓰는 모델용 — [CLS] 토큰 임베딩을 뽑아 L2 정규화."""
    import torch
    from transformers import AutoModel, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    model.eval()

    vectors = []
    with torch.no_grad():
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            inputs = tokenizer(batch, padding=True, truncation=True, max_length=512, return_tensors="pt")
            outputs = model(**inputs)
            cls = outputs.last_hidden_state[:, 0, :]  # [CLS] 토큰
            cls = torch.nn.functional.normalize(cls, p=2, dim=1)
            vectors.append(cls.numpy())
    return np.concatenate(vectors, axis=0)


def encode(model_name: str, texts: list[str]) -> np.ndarray:
    if model_name in POOLING_OVERRIDES:
        return encode_cls_pooling(model_name, texts)
    return encode_sentence_transformers(model_name, texts)


def evaluate_model(model_name: str, corpus: list[dict], queries: list[dict]) -> dict:
    corpus_ids = [row["id"] for row in corpus]
    corpus_texts = [row["text"] for row in corpus]

    t0 = time.time()
    corpus_vectors = encode(model_name, corpus_texts)
    query_vectors = encode(model_name, [q["query"] for q in queries])
    elapsed = time.time() - t0

    recalls = {k: [] for k in K_VALUES}
    rr_scores = []

    sims = query_vectors @ corpus_vectors.T  # 정규화된 벡터라 내적 = 코사인 유사도
    for row_idx, q in enumerate(queries):
        ranked_idx = np.argsort(-sims[row_idx])
        ranked_ids = [corpus_ids[i] for i in ranked_idx]
        for k in K_VALUES:
            recalls[k].append(recall_at_k(ranked_ids, q["relevant_id"], k))
        rr_scores.append(reciprocal_rank(ranked_ids, q["relevant_id"]))

    return {
        "model": model_name,
        "dim": corpus_vectors.shape[1],
        "n": len(corpus_texts),
        "encode_seconds": round(elapsed, 1),
        "mrr": round(float(np.mean(rr_scores)), 4),
        **{f"recall@{k}": round(float(np.mean(v)), 4) for k, v in recalls.items()},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", type=str, default=None, help="쉼표로 구분된 HF 모델 이름 목록")
    parser.add_argument("--limit", type=int, default=None, help="코퍼스/쿼리를 이 개수만큼만 잘라서 빠르게 테스트")
    args = parser.parse_args()

    models = [m.strip() for m in args.models.split(",")] if args.models else DEFAULT_MODELS

    corpus = load_jsonl(EVAL_DIR / "embedding_corpus.jsonl")
    queries = load_jsonl(EVAL_DIR / "embedding_queries.jsonl")
    if args.limit:
        corpus = corpus[: args.limit]
        corpus_ids = {row["id"] for row in corpus}
        queries = [q for q in queries[: args.limit] if q["relevant_id"] in corpus_ids]

    print(f"코퍼스 {len(corpus)}개, 쿼리 {len(queries)}개로 평가\n")

    results = []
    for model_name in models:
        print(f"--- {model_name} 인코딩 중 (CPU라 시간 좀 걸림) ---")
        result = evaluate_model(model_name, corpus, queries)
        results.append(result)
        print(result, "\n")

    print("=== 요약 ===")
    header = ["model", "dim", "n", "encode_seconds", "mrr"] + [f"recall@{k}" for k in K_VALUES]
    print(" | ".join(header))
    for r in results:
        print(" | ".join(str(r[h]) for h in header))


if __name__ == "__main__":
    main()
