"""RAG 데이터셋 실제 ingestion CLI. `ai.rag.ingestion`(순수, DB 모름)과 backend
(DB/설정)를 둘 다 import할 수 있는 곳은 `ai/rag`도 `backend/app`도 아니라서(둘 중
어느 쪽도 서로를 몰라야 함) scripts/ 아래 별도 진입점으로 뒀다.

DATABASE_URL/EMBEDDING_*/HF_TOKEN 등은 전부 backend.app.core.config.Settings가
읽는 .env 경로 그대로 쓴다 - 코드에 하드코딩된 값은 없다. Colab에서 실행할 때도
이 스크립트를 그대로 쓰고, 해당 환경의 .env(또는 Colab secrets를 .env로 떨어뜨린
파일)만 바꿔주면 된다.

사용법:
    python scripts/rag_ingest.py --source asan --dry-run --limit 20
    python scripts/rag_ingest.py --source asan --limit 80          # 실제 Neon 적재
"""
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from ai.rag.ingestion.adapters.registry import ADAPTERS  # noqa: E402
from ai.rag.ingestion.dedup import Deduplicator, content_hash, load_hash_index, save_hash_index  # noqa: E402

# scripts/rag_prepare_dataset.py(로컬 파일만 만드는 검증/감사용 스크립트)와는
# **일부러 다른 파일**을 쓴다 - 한때 같은 파일을 공유했다가 실제 버그가 났다:
# 로컬 전처리를 테스트 삼아 여러 번 돌리면서(청킹 버그 수정 등으로 재시작 반복)
# asan 전체가 "이미 처리한 내용"으로 그 파일에 기록됐는데, 그 로컬 실행들은
# 실제로 Neon에 아무것도 저장한 적이 없었다. 그런데도 나중에 실제 저장을 실행하니
# asan 19,156행이 전부 중복 처리되어 하나도 안 들어가는 버그가 났다(cleaned_count=0).
# 로컬 감사용 실행과 실제 저장은 개념이 다르므로(하나는 "본 적 있다", 다른 하나는
# "실제로 Neon에 있다") 완전히 분리한다. 신뢰도 tier 순서(scripts/_run_all_rag_ingest.sh)
# 로 먼저 처리되는 쪽이 원본으로 남는 건 이 파일 안에서만 유효하다.
#
# **이 파일을 분리해도 같은 부류의 버그가 재발한 적이 있다(2026-09-02)**:
# Deduplicator.is_duplicate()는 파이프라인이 레코드를 "본 순간"(DB 저장 성공
# 여부와 무관하게) 내부 seen-set에 기록한다. 그런데 예전에는 이 실행이 끝나면
# `deduplicator.snapshot()`(이번 실행에서 "본" 모든 것)을 그대로 저장했다 -
# Neon 용량 초과로 저장이 실패하는 동안에도 파이프라인은 계속 레코드를 "보고"
# 있었고, 그게 전부 중복 인덱스에 영구 기록돼버렸다. 그 결과 나중에 용량 문제를
# 고쳐도 asan/snuh-clinical-qa/health-search-qa는 재실행 시 전부 0건으로
# 나오는 버그가 실제로 발생했다(문서 61%/9.6%/2.2%만 저장된 상태에서 "더 넣을
# 게 없다"고 나옴). 그래서 지금은 `deduplicator.snapshot()`을 그대로 쓰지 않고
# `run_bulk_ingestion()`이 반환하는 `result.committed_records`(실제로 Neon에
# durable하게 존재함이 확인된 것만)의 해시만 반영한다.
_CROSS_DATASET_INDEX_FILENAME = "_cross_dataset_dedup_index.neon.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RAG 데이터셋 ingestion (실제 Neon 적재 가능)")
    parser.add_argument("--source", required=True, choices=sorted(ADAPTERS))
    parser.add_argument("--dry-run", action="store_true", help="DB에 아무것도 쓰지 않고 통계만 출력")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--shuffle-seed",
        type=int,
        default=None,
        help="--limit과 같이 쓰면 '앞에서부터 N개'가 아니라 전체에서 고르게 뽑은 N개가 된다",
    )
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--data-dir", default=str(PROJECT_ROOT / "data"), help="cross-dataset dedup index 저장 위치")
    args = parser.parse_args(argv)

    # backend 쪽 import는 sys.path 세팅 이후에 해야 한다.
    from app.core.database import SessionLocal
    from app.services.rag_bulk_ingestion_service import print_report, run_bulk_ingestion

    dedup_index_path = Path(args.data_dir) / _CROSS_DATASET_INDEX_FILENAME
    original_seed = load_hash_index(dedup_index_path)
    deduplicator = Deduplicator(seed=original_seed)

    db = SessionLocal()
    try:
        result = run_bulk_ingestion(
            args.source,
            db,
            limit=args.limit,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
            deduplicator=deduplicator,
            shuffle_seed=args.shuffle_seed,
        )
    except PermissionError as exc:
        print(f"Dataset: {args.source}")
        print(f"FAILED: {exc}")
        return 1
    finally:
        db.close()

    # dry-run이어도 저장한다 - dry-run 단계에서 미리 확인한 cross-dataset 중복
    # 판단이 실제 실행 때도 똑같이 이어지도록(dry-run 신뢰성 원칙, 파일 상단 참고).
    # `deduplicator.snapshot()`이 아니라 `original_seed`(이전 실행까지 확정된 것)
    # + `result.committed_records`(이번 실행에서 실제로 Neon에 durable하게 존재함이
    # 확인된 것)만 반영한다 - 파일 상단 주석 참고(용량 초과 등으로 저장이 실패한
    # 레코드까지 "처리했다"고 영구 기록하면 안 된다).
    persisted_hashes = original_seed | {content_hash(record) for record in result.committed_records}
    save_hash_index(dedup_index_path, persisted_hashes)

    print_report(result)
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
