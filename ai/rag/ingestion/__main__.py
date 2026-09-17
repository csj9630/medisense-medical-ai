"""dry-run 전용 CLI. `ai/rag`는 backend/SQLAlchemy를 몰라야 하므로, 여기서는 실제
Neon 저장은 절대 하지 않는다 - 실제 저장이 필요한 실행은 `scripts/rag_ingest.py`를
쓴다(둘 다 내부적으로 같은 run_ingestion_pipeline()을 쓰므로 dry-run 결과와 실제
실행 결과의 앞부분 통계는 항상 일치한다).

사용법:
    python -m ai.rag.ingestion --source asan --dry-run --limit 500
"""
import argparse
import sys

from .adapters.registry import ADAPTERS, get_adapter
from .pipeline import run_ingestion_pipeline


def _print_report(result) -> None:  # noqa: ANN001 - IngestionPipelineResult, 순환 import 피하려고 타입힌트 생략
    print(f"Dataset: {result.source}")
    print(f"Raw: {result.raw_count}")
    print(f"After cleaning: {result.cleaned_count}")
    print(f"After deduplication: {result.documents_count}")
    print(f"Documents: {result.documents_count}")
    print(f"Chunks: {result.chunk_count}")
    print("Jina embeddings: skipped(dry-run)")
    print("BGE embeddings: skipped(dry-run)")
    print("Inserted: skipped(dry-run)")
    print(f"Duplicates removed: {result.duplicate_count}")
    print("Failed: 0")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RAG 데이터셋 ingestion dry-run")
    parser.add_argument("--source", required=True, choices=sorted(ADAPTERS), help="데이터셋 어댑터 이름")
    parser.add_argument("--dry-run", action="store_true", help="이 모듈에서는 항상 dry-run(무시됨, 명시용)")
    parser.add_argument("--limit", type=int, default=None, help="스트리밍으로 읽을 최대 행 수")
    args = parser.parse_args(argv)

    try:
        adapter = get_adapter(args.source)
        result = run_ingestion_pipeline(adapter, limit=args.limit)
    except PermissionError as exc:
        print(f"Dataset: {args.source}")
        print(f"FAILED: {exc}")
        return 1

    _print_report(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
