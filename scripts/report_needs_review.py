"""ingestion 시점에 chunk_metadata.needs_review=true로 표시된 청크들을 카테고리별로
집계한다. 사람 검수 화면을 만들기 전 단계 - "얼마나 있는지, 어떤 종류가 많은지"부터
숫자로 확인하기 위한 리포트다.

needs_review 자체는 ai/rag/ingestion/quality.py의 단일 불리언 플래그라 "왜"
걸렸는지는 저장 안 해뒀다. 그래서 여기서 저장된 chunk_text에 그 파일의 키워드
정규식을 카테고리별로 다시 적용해서 사후 집계한다 - quality.py의 판정 기준과
반드시 같은 키워드를 써야 "needs_review 총합"과 "카테고리별 합"이 서로 안 맞는
착시가 안 생긴다(한 청크가 여러 카테고리에 동시에 걸릴 수 있어 카테고리 합은
총합보다 클 수 있음 - 정상).
"""
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

# ai/rag/ingestion/quality.py의 _NEEDS_REVIEW_PATTERN과 반드시 같은 키워드를 쓴다.
_CATEGORIES = {
    "응급/긴급": re.compile(r"(응급|긴급)"),
    "처방/투여": re.compile(r"(처방|투여)"),
    "용량": re.compile(r"용량"),
    "수술 적응": re.compile(r"수술\s*적응"),
    "확진/진단기준": re.compile(r"(확진|진단\s*기준)"),
    "가이드라인": re.compile(r"가이드라인"),
    "금기": re.compile(r"금기"),
    "부작용": re.compile(r"부작용"),
}


def main() -> int:
    from sqlalchemy import text

    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        total_chunks = db.execute(text("SELECT count(*) FROM vector_db.document_chunks")).scalar()
        needs_review_rows = db.execute(
            text(
                """
                SELECT chunk_text
                FROM vector_db.document_chunks
                WHERE metadata->>'needs_review' = 'true'
                """
            )
        ).fetchall()
    finally:
        db.close()

    needs_review_count = len(needs_review_rows)
    category_counts = {name: 0 for name in _CATEGORIES}
    for (chunk_text,) in needs_review_rows:
        for name, pattern in _CATEGORIES.items():
            if pattern.search(chunk_text):
                category_counts[name] += 1

    print(f"총 chunk       {total_chunks:>8,}")
    print(f"needs_review   {needs_review_count:>8,}  ({needs_review_count / total_chunks:.1%})" if total_chunks else "needs_review   0")
    print()
    print("카테고리별 (한 청크가 여러 카테고리에 겹칠 수 있음):")
    for name, count in sorted(category_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {name:<14} {count:>8,}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
