"""저장된 document_chunks를 규칙 기반으로 훑어서 품질 신호를 카테고리별로
집계한다. 아무것도 지우거나 고치지 않는다 - 통계와 샘플만 보여준다(사람이
판단하기 전에 먼저 "얼마나, 어떤 모양으로" 있는지 확인하기 위함).

**"문장 중간 절단" 판정의 한계**: chunking.py는 overlap 기반이라 한 문서가 여러
청크로 나뉘는 게 정상이고, 마지막 청크가 아닌 청크가 문장부호 없이 끝나는 것
자체는 전혀 이상하지 않다(다음 청크로 이어질 뿐). 진짜 문제는 "문장 하나가
예산을 넘어서 토큰 단위로 강제 분할된" 드문 경우인데, 저장된 데이터에는 그
구분이 안 남아있다. 그래서 여기서는 "일반적인 한국어 종결 어미/문장부호로 안
끝난다"를 느슨한 대리 신호로만 쓴다 - 과다 추정(false positive)이 섞일 수
있다는 걸 알고 리포트를 읽어야 한다(그래서 자동 삭제가 아니라 샘플 확인 용도).
"""
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from ai.rag.ingestion.cleaning import _ALLOWED_CHARS, _JUNK_RATIO_THRESHOLD  # noqa: E402

TOO_SHORT_CHARS = 30
TOO_LONG_CHARS = 2000  # DEFAULT_MAX_TOKENS=300 기준 한글은 1토큰≈1~2자라 넉넉히 잡음

_SENTENCE_FINAL_ENDINGS = (".", "!", "?", ")", "다", "요", "죠", "까", "음", "함", "됨")

# chunking.py의 문장 분리 정규식과 같은 구두점 기준 - 한 청크 안에서 문장을
# 나눠서 "같은 문장이 반복되는지"를 본다(inline 반복은 response_validator.py에서
# 실제 관찰된 문제와 같은 부류).
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。！？])\s+")


def _is_too_short(text: str) -> bool:
    return len(text.strip()) < TOO_SHORT_CHARS


def _is_too_long(text: str) -> bool:
    return len(text) > TOO_LONG_CHARS


def _is_meaningless(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    junk = len(_ALLOWED_CHARS.sub("", stripped))
    return (junk / len(stripped)) > _JUNK_RATIO_THRESHOLD


def _looks_mid_sentence_cut(text: str) -> bool:
    stripped = text.rstrip()
    if not stripped:
        return False
    return not stripped.endswith(_SENTENCE_FINAL_ENDINGS)


def _has_excessive_repetition(text: str) -> bool:
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    if len(sentences) < 3:
        return False
    most_common = max((sentences.count(s) for s in set(sentences)), default=0)
    return most_common >= 3


def main() -> int:
    from sqlalchemy import text as sql_text

    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        rows = db.execute(
            sql_text("SELECT id, chunk_text, metadata FROM vector_db.document_chunks")
        ).fetchall()
    finally:
        db.close()

    total = len(rows)
    flags: dict[str, list[str]] = {
        "too_short": [],
        "too_long": [],
        "meaningless": [],
        "mid_sentence_cut": [],
        "excessive_repetition": [],
        "metadata_missing": [],
    }

    for chunk_id, chunk_text, metadata in rows:
        if _is_too_short(chunk_text):
            flags["too_short"].append(chunk_text)
        if _is_too_long(chunk_text):
            flags["too_long"].append(chunk_text)
        if _is_meaningless(chunk_text):
            flags["meaningless"].append(chunk_text)
        if _looks_mid_sentence_cut(chunk_text):
            flags["mid_sentence_cut"].append(chunk_text)
        if _has_excessive_repetition(chunk_text):
            flags["excessive_repetition"].append(chunk_text)
        if not metadata or not metadata.get("source"):
            flags["metadata_missing"].append(chunk_text)

    print(f"총 chunk {total:,}")
    print()
    for name, samples in flags.items():
        pct = len(samples) / total if total else 0
        print(f"{name:<22} {len(samples):>8,}  ({pct:.1%})")

    print()
    print("=== 샘플 (각 카테고리 최대 3개) ===")
    for name, samples in flags.items():
        if not samples:
            continue
        print(f"\n[{name}]")
        for s in samples[:3]:
            preview = s.strip().replace("\n", " ")
            preview = preview[:120] + ("…" if len(preview) > 120 else "")
            print(f"  - {preview!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
