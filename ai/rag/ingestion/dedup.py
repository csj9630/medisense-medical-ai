"""문서 단위 중복 판정. 청크 단위가 아니라 정규화된 문서(chunking 이전) 단위로
해시를 낸다 - 한 문서가 통째로 스킵되거나 안 되거나 둘 중 하나로 취급하면 충분하고,
저장 단계의 재실행 시 skip(idempotency)은 document_id 역할을 하는 합성 URL로
따로 처리한다(backend 쪽 rag_bulk_ingestion_service.py, original_id가 그 URL의
일부가 된다).

**해시 기준에 source/original_dataset을 넣지 않는다** - 처음엔 데이터셋별로만
중복을 잡았지만, 실제로 여러 데이터셋(예: snuh-clinical-qa, komed-instruct)에
같은 설명이 반복해서 실리는 경우가 있어서 "다른 데이터셋이어도 내용이 같으면
중복"으로 바꿨다. `Deduplicator`가 여러 데이터셋에 걸쳐 재사용되면(seed/snapshot로
디스크에 저장된 이전 실행 결과를 이어받으면) 자동으로 데이터셋 간 중복도 잡힌다 -
어느 쪽이 "원본으로 남을지"는 호출 순서(먼저 처리되는 쪽이 이김)로 정해지므로,
신뢰도 높은 데이터셋을 먼저 처리해야 한다(scripts/_run_all_rag_prepare.sh 참고).

**의도적으로 original_id는 해시에 안 넣는다.** 이 모듈의 목적은 "서로 다른 행인데
내용이 완전히 같은 경우"(예: 같은 설명이 다른 질문 문구로 두 번 실림)를 잡는
것이라, original_id까지 해시에 포함하면 그런 진짜 중복을 절대 못 잡는다 -
original_id가 다르면 항상 다른 해시가 나와버리기 때문이다. original_id는
idempotency(재실행 skip) 쪽에서만 쓴다.
"""
import hashlib
import json
from pathlib import Path

from .schema import NormalizedRecord


def content_hash(record: NormalizedRecord) -> str:
    return hashlib.sha256(record.content.strip().encode("utf-8")).hexdigest()


class Deduplicator:
    """중복 여부를 추적하는 아주 단순한 래퍼. 상태는 set 하나뿐이지만, 데이터셋
    여러 개(별도 프로세스로 실행되는 경우 포함)에 걸쳐 이어 쓸 수 있도록
    seed()/snapshot()으로 내부 set을 내보내고 불러올 수 있다."""

    def __init__(self, seed: set[str] | None = None) -> None:
        self._seen: set[str] = set(seed) if seed else set()

    def is_duplicate(self, record: NormalizedRecord) -> bool:
        h = content_hash(record)
        if h in self._seen:
            return True
        self._seen.add(h)
        return False

    def snapshot(self) -> set[str]:
        return set(self._seen)


def load_hash_index(path: Path) -> set[str]:
    """이전 실행(다른 데이터셋)이 저장해둔 해시 목록을 읽는다. 파일이 없으면
    빈 set(첫 실행)."""
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as f:
        return set(json.load(f))


def save_hash_index(path: Path, hashes: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(sorted(hashes), f)
