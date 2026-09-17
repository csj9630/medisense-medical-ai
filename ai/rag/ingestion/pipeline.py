"""순수 ingestion 파이프라인: load -> normalize -> clean -> dedup -> chunk.
DB/backend를 전혀 모른다(ai/rag/CLAUDE.md 규칙) - 결과는 메모리 위의
`IngestionPipelineResult`로만 나간다. 실제 저장은 backend 쪽
(rag_bulk_ingestion_service.py)이 이 결과를 받아서 처리한다.
"""
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

from ..chunking import Chunk, chunk_text
from .adapters.base import DatasetAdapter
from .cleaning import clean_content
from .dedup import Deduplicator
from .quality import detect_needs_review
from .schema import NormalizedRecord


@dataclass(frozen=True)
class IngestionRecord:
    normalized: NormalizedRecord
    chunks: list[Chunk]
    document_metadata: dict


@dataclass
class IngestionSink:
    """파이프라인 각 단계 결과를 옆에서 지켜보기만 하는 훅 모음 - 실제 DB/디스크
    저장은 이 콜백을 채워 넘기는 호출부(예: 로컬 raw/processed/chunks JSONL로
    남기고 싶은 스크립트) 책임이고, 파이프라인 로직 자체는 sink가 있든 없든 완전히
    동일하게 동작한다(순수 관찰자 - 반환값을 보지 않고, 예외를 던져도 삼키지 않는다).
    """

    on_raw: Callable[[dict[str, Any]], None] | None = None
    # 정제(clean_content)까지 통과했지만 아직 중복 판정 전인 레코드.
    on_normalized: Callable[[NormalizedRecord], None] | None = None
    # 정제 + 중복 제거까지 살아남은, chunking 직전의 레코드("processed" 단계).
    on_processed: Callable[[NormalizedRecord], None] | None = None
    on_duplicate: Callable[[NormalizedRecord], None] | None = None
    on_record: Callable[[IngestionRecord], None] | None = None


@dataclass
class IngestionPipelineResult:
    source: str
    raw_count: int = 0
    cleaned_count: int = 0
    duplicate_count: int = 0
    chunk_count: int = 0
    records: list[IngestionRecord] = field(default_factory=list)
    # 어댑터별 품질 필터가 무엇을 걸렀는지/고쳤는지 (예: {"rejected_ai_refusal": 4,
    # "stripped_answer_restatement": 229}) - adapter.filter_stats 그대로. 필터가
    # 없는 어댑터는 빈 dict.
    filter_stats: dict[str, int] = field(default_factory=dict)

    @property
    def documents_count(self) -> int:
        return len(self.records)


def build_document_metadata(record: NormalizedRecord, *, needs_review: bool) -> dict:
    """청크 저장용 metadata dict - message(5) 8번 섹션 스키마 예시와 최대한
    일관되게 맞춘다. 원본에 있던 값과 이 함수가 만들어낸 값(reliability 기본값,
    needs_review)을 구분할 수 있도록 generated_metadata는 어댑터가 이미 설정해둔
    값을 우선하고, 없으면 False로 채운다(아무것도 새로 추론하지 않았다는 뜻)."""
    metadata = dict(record.metadata)
    metadata.setdefault("source", record.source)
    metadata.setdefault("source_type", record.source_type)
    metadata.setdefault("language", "ko")
    metadata.setdefault("category", record.category)
    metadata.setdefault("department", record.department)
    metadata.setdefault("disease", record.disease)
    metadata.setdefault("symptoms", record.symptoms)
    # 각 어댑터가 실제 HF dataset card(출처/생성방식/검수여부)를 확인하고 이미
    # metadata에 reliability를 채워둔다(adapters/*.py 참고) - 여기는 어댑터가
    # 깜빡한 경우에만 쓰이는 안전망 기본값이라 "확인 안 됨"으로만 채운다(추측 금지).
    metadata.setdefault("reliability", "unspecified")
    metadata.setdefault("reliability_tier", "확인 필요")
    metadata.setdefault("original_dataset", record.original_dataset)
    metadata.setdefault("original_id", record.original_id)
    metadata.setdefault("generated_metadata", False)
    metadata["needs_review"] = needs_review
    return metadata


def run_ingestion_pipeline(
    adapter: DatasetAdapter,
    *,
    limit: int | None = None,
    sink: IngestionSink | None = None,
    deduplicator: Deduplicator | None = None,
    shuffle_seed: int | None = None,
) -> IngestionPipelineResult:
    """`deduplicator`를 안 넘기면(기본) 이 실행 안에서만 중복을 잡는다. 여러
    데이터셋에 걸친 중복까지 잡으려면, 이전 데이터셋 처리에서 나온
    `Deduplicator.snapshot()`으로 seed한 인스턴스를 넘기면 된다(scripts/
    rag_prepare_dataset.py가 디스크에 저장된 snapshot을 이어받아 이렇게 쓴다).

    `shuffle_seed` + `limit`을 같이 쓰면 "앞에서부터 N개"가 아니라 스트림 전체에서
    고르게 뽑은 N개가 된다(adapter.load_raw 참고) - 원본 데이터가 큰데 일부만
    쓸 때(예: komed-instruct 8,000건) 위치 편향을 피하고 싶을 때 쓴다."""
    result = IngestionPipelineResult(source=adapter.source)
    deduplicator = deduplicator or Deduplicator()
    sink = sink or IngestionSink()

    for index, raw_row in enumerate(adapter.load_raw(limit, shuffle_seed=shuffle_seed)):
        result.raw_count += 1
        if sink.on_raw:
            sink.on_raw(dict(raw_row))

        normalized = adapter.to_normalized(raw_row, index)
        if normalized is None:
            continue

        cleaned_content = clean_content(normalized.content)
        if cleaned_content is None:
            continue
        if cleaned_content != normalized.content:
            normalized = _with_content(normalized, cleaned_content)
        if sink.on_normalized:
            sink.on_normalized(normalized)

        if deduplicator.is_duplicate(normalized):
            result.duplicate_count += 1
            if sink.on_duplicate:
                sink.on_duplicate(normalized)
            continue
        result.cleaned_count += 1
        if sink.on_processed:
            sink.on_processed(normalized)

        chunks = chunk_text(normalized.content)
        if not chunks:
            continue

        doc_metadata = build_document_metadata(
            normalized, needs_review=detect_needs_review(normalized.content)
        )
        record = IngestionRecord(normalized, chunks, doc_metadata)
        result.records.append(record)
        result.chunk_count += len(chunks)
        if sink.on_record:
            sink.on_record(record)

    result.filter_stats = dict(getattr(adapter, "filter_stats", {}))
    return result


def _with_content(record: NormalizedRecord, content: str) -> NormalizedRecord:
    """NormalizedRecord가 frozen dataclass라 content만 바꾼 새 인스턴스를 만든다
    (clean_content가 앞뒤 공백만 정리했을 뿐이라 다른 필드는 그대로 복사)."""
    return replace(record, content=content)
