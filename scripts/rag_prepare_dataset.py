"""HuggingFace RAG 데이터셋을 실제 Neon에는 아무것도 쓰지 않고, 로컬 파일로 raw ->
processed -> chunk -> (Jina v4/Medical BGE-M3) embedding까지 전부 끝낸 상태로 남긴다.

실제 Neon 저장(팀원이 직접 담당하기로 함)은 이 스크립트의 책임이 아니다 - 필요할 때
`scripts/rag_ingest.py`가 그 역할을 그대로 수행한다(이 스크립트가 만든 로컬 파일과는
독립적으로, HF에서 다시 스트리밍해서 저장한다).

임베딩 자체는 원격 API 호출(로컬 GPU 불필요)이라 Colab 없이 이 스크립트 그대로
실행하면 된다. DATABASE_URL은 전혀 안 쓰지만, 임베딩 접속 정보(EMBEDDING_*)는
backend의 기존 provider 팩토리(`app.core.rag_embedding`)를 그대로 재사용하기 위해
backend 쪽 import가 필요하다 - `ai/rag`는 backend를 몰라야 하므로(ai/rag/CLAUDE.md),
`scripts/rag_ingest.py`와 동일하게 이 스크립트가 다리 역할을 한다.

출력 구조 (팀원 지시서 25번 섹션 형식 그대로):
    data/raw/<source>.jsonl        원본 그대로(정제 전, HF 원본 dict)
    data/processed/<source>.jsonl  정제 + 중복 제거 통과 (chunking 전 NormalizedRecord)
    data/chunks/<source>.jsonl     의미 단위 청킹 + metadata 완료 (문서 단위, 청크 배열 포함)
    data/embeddings/<source>.jsonl 청크별 Jina v4 / Medical BGE-M3 벡터(정규화됨)

사용법:
    python scripts/rag_prepare_dataset.py --source asan --limit 200
    python scripts/rag_prepare_dataset.py --source asan               # 전체 스트리밍
    python scripts/rag_prepare_dataset.py --source asan --skip-embeddings  # 벡터화 제외, 청킹까지만
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from ai.rag.ingestion.adapters.registry import ADAPTERS, get_adapter  # noqa: E402
from ai.rag.ingestion.dedup import Deduplicator, load_hash_index, save_hash_index  # noqa: E402
from ai.rag.ingestion.pipeline import IngestionSink, run_ingestion_pipeline  # noqa: E402
from ai.rag.ingestion.schema import NormalizedRecord  # noqa: E402

# 여러 데이터셋(별도 프로세스로 하나씩 실행됨)에 걸친 중복 제거를 위해 이전
# 실행이 남긴 content hash 목록을 여기 저장/공유한다. 신뢰도 높은 데이터셋을
# 먼저 처리해야 그쪽이 "원본"으로 남는다 - scripts/_run_all_rag_prepare.sh의
# 실행 순서(신뢰도 tier 순)를 반드시 지킬 것.
_CROSS_DATASET_INDEX_FILENAME = "_cross_dataset_dedup_index.json"


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _normalized_to_dict(record: NormalizedRecord) -> dict[str, Any]:
    return {
        "source": record.source,
        "source_type": record.source_type,
        "content": record.content,
        "original_id": record.original_id,
        "original_dataset": record.original_dataset,
        "title": record.title,
        "question": record.question,
        "answer": record.answer,
        "category": record.category,
        "department": record.department,
        "disease": record.disease,
        "symptoms": record.symptoms,
        "metadata": record.metadata,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="RAG 데이터셋을 로컬 파일로 전처리(raw/processed/chunks/embeddings) - Neon에는 안 씀"
    )
    parser.add_argument("--source", required=True, choices=sorted(ADAPTERS))
    parser.add_argument("--limit", type=int, default=None, help="생략하면 전체 스트리밍")
    parser.add_argument(
        "--shuffle-seed",
        type=int,
        default=None,
        help="--limit과 같이 쓰면 '앞에서부터 N개'가 아니라 전체에서 고르게 뽑은 N개가 된다",
    )
    parser.add_argument("--out-dir", default=str(PROJECT_ROOT / "data"))
    parser.add_argument(
        "--skip-embeddings", action="store_true", help="벡터화는 건너뛰고 청킹까지만 로컬에 남긴다"
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)

    try:
        adapter = get_adapter(args.source)
    except ValueError as exc:
        print(f"FAILED: {exc}")
        return 1

    raw_rows: list[dict[str, Any]] = []
    processed_rows: list[dict[str, Any]] = []
    sink = IngestionSink(
        on_raw=raw_rows.append,
        on_processed=lambda record: processed_rows.append(_normalized_to_dict(record)),
    )

    # 여러 데이터셋에 걸친 중복 제거 - 이전에 처리한(신뢰도 더 높은) 데이터셋이
    # 남긴 hash 목록을 이어받는다. 처음 실행이면 빈 set(파일 없음)에서 시작.
    dedup_index_path = out_dir / _CROSS_DATASET_INDEX_FILENAME
    deduplicator = Deduplicator(seed=load_hash_index(dedup_index_path))

    try:
        result = run_ingestion_pipeline(
            adapter,
            limit=args.limit,
            sink=sink,
            deduplicator=deduplicator,
            shuffle_seed=args.shuffle_seed,
        )
    except PermissionError as exc:
        # gated 데이터셋(예: AI_healthcare_QA) - 추측으로 처리하지 않고 그대로 실패 보고.
        print(f"Dataset: {args.source}")
        print(f"FAILED (gated): {exc}")
        return 1

    save_hash_index(dedup_index_path, deduplicator.snapshot())

    chunk_rows: list[dict[str, Any]] = []
    all_chunks_flat: list[tuple[str, int, str]] = []
    for record in result.records:
        chunk_rows.append(
            {
                "original_id": record.normalized.original_id,
                "original_dataset": record.normalized.original_dataset,
                "source": record.normalized.source,
                "chunks": [
                    {"chunk_index": c.index, "text": c.text, "token_count": c.token_count}
                    for c in record.chunks
                ],
                "metadata": record.document_metadata,
            }
        )
        for c in record.chunks:
            all_chunks_flat.append((record.normalized.original_id, c.index, c.text))

    _write_jsonl(out_dir / "raw" / f"{args.source}.jsonl", raw_rows)
    _write_jsonl(out_dir / "processed" / f"{args.source}.jsonl", processed_rows)
    _write_jsonl(out_dir / "chunks" / f"{args.source}.jsonl", chunk_rows)

    print(f"Dataset: {adapter.source}")
    print(f"Raw: {result.raw_count}")
    print(f"After cleaning: {result.cleaned_count + result.duplicate_count}")
    print(f"After deduplication: {result.cleaned_count}")
    print(f"Documents: {result.documents_count}")
    print(f"Chunks: {result.chunk_count}")

    if args.skip_embeddings:
        print("Jina embeddings: skipped (--skip-embeddings)")
        print("BGE embeddings: skipped (--skip-embeddings)")
        print(f"Saved to: {out_dir}")
        return 0

    if not all_chunks_flat:
        print("Jina embeddings: 0 (청크 없음)")
        print("BGE embeddings: 0 (청크 없음)")
        print(f"Saved to: {out_dir}")
        return 0

    # 임베딩 계산 - backend가 이미 갖고 있는 provider 팩토리를 그대로 재사용한다
    # (ai/rag는 backend를 모르므로, scripts/ 층에서만 두 세계를 연결).
    from app.core.rag_embedding import get_default_rag_embedding_providers

    providers = get_default_rag_embedding_providers()
    texts = [text for (_, _, text) in all_chunks_flat]

    embedding_rows: list[dict[str, Any]] = []
    for provider in providers:
        vectors = provider.embed_texts(texts)
        for (original_id, chunk_index, _), vector in zip(all_chunks_flat, vectors):
            embedding_rows.append(
                {
                    "original_id": original_id,
                    "original_dataset": adapter.hf_path,
                    "chunk_index": chunk_index,
                    "provider": provider.name,
                    "dimension": len(vector),
                    "vector": vector,
                }
            )
        print(f"{provider.name} embeddings: {len(vectors)}")

    _write_jsonl(out_dir / "embeddings" / f"{args.source}.jsonl", embedding_rows)
    print(f"Saved to: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
