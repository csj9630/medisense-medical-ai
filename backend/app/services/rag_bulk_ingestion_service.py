"""ai/rag/ingestion(순수 파이썬)과 실제 DB 저장(ai/consultation과 같은 계층 원칙 -
ai/*는 backend/app을 모르지만 backend/app은 ai/*를 알 수 있다) 사이의 다리.

dry-run과 실제 실행이 정확히 같은 "이미 있으면 스킵" 판단 로직을 타도록 만들었다 -
dry-run이 "몇 건 스킵될지"를 미리 보여주는 게 곧 실제 실행에서 스킵될 건수와
같아야 dry-run을 신뢰할 수 있다.

**왜 `document_ingestion_service.ingest_document()`를 안 쓰는가**: 그 함수는 문서
하나(OCR 업로드 한 건)를 실시간으로 처리하는 용도라 문서당 임베딩 API 호출 +
문서당 여러 번 커밋을 한다. 대량 ingestion(문서 수천~수만 건)에 그대로 쓰면
문서 하나당 네트워크 왕복이 여러 번 생겨서 실제로 asan 20건에 약 3분이 걸렸다
(전체 데이터셋으로 환산하면 수십 시간). 그래서 이 파일은 `batch_size`개 문서를
모아서 임베딩 API를 한 번에(문서 여러 개의 청크를 합쳐서) 호출하고, DB도 배치당
한 번만 커밋한다 - repository의 `commit=False` 옵션이 이걸 위한 것이다.
"""
from dataclasses import dataclass, field

from ai.rag import EmbeddingProvider
from ai.rag.ingestion.adapters.registry import get_adapter
from ai.rag.ingestion.dedup import Deduplicator
from ai.rag.ingestion.pipeline import run_ingestion_pipeline
from ai.rag.ingestion.schema import NormalizedRecord
from app.core.logging import get_logger
from app.core.rag_embedding import get_default_rag_embedding_providers
from app.models.generated import AdminDocuments, DocumentChunks
from app.repositories.admin_document import AdminDocumentRepository
from app.repositories.document_chunk import DocumentChunkRepository

logger = get_logger("services.rag_bulk_ingestion")


@dataclass
class BulkIngestionResult:
    source: str
    raw_count: int = 0
    cleaned_count: int = 0
    duplicate_count: int = 0
    chunk_count: int = 0
    documents_ingested: int = 0
    chunks_ingested: int = 0
    skipped_existing: int = 0
    dry_run: bool = False
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    shuffle_seed: int | None = None
    # 어댑터 품질 필터가 무엇을 걸렀는지/고쳤는지 (komed_instruct.py 등 - 필터
    # 없는 데이터셋은 빈 dict). pipeline.py의 IngestionPipelineResult.filter_stats
    # 그대로.
    filter_stats: dict[str, int] = field(default_factory=dict)
    # 실제로 만들어진 문서들의 source_tier/verification_status 분포 - "저장은
    # 됐는데 신뢰도가 어떻게 섞였는지"를 저장 시점에 바로 확인하기 위함.
    source_tier_counts: dict[str, int] = field(default_factory=dict)
    verification_status_counts: dict[str, int] = field(default_factory=dict)
    # 실제로 Neon에 durable하게 존재하는(이번에 새로 커밋됐거나, 이미 이전 실행에서
    # 커밋되어 있어 이번엔 skipped_existing으로 건너뛴) 레코드만 담는다 - 호출부
    # (scripts/rag_ingest.py)가 cross-dataset dedup 인덱스를 저장할 때 여기 담긴
    # 것만 반영해야 한다. pipeline_result.records 전체를 쓰면 안 된다: DB 저장이
    # 실패한(예: Neon 용량 초과) 레코드까지 "처리했다"고 영구 기록해버려서, 나중에
    # 문제를 고쳐도 그 레코드들이 다시는 시도되지 않는 버그가 실제로 있었다
    # (asan/snuh-clinical-qa/health-search-qa가 재실행 시 전부 0건으로 나옴).
    committed_records: list[NormalizedRecord] = field(default_factory=list)


def _synthetic_url(source: str, original_id: str) -> str:
    # admin_ocr.py의 "ocr-job://{job_id}/{name}" 플레이스홀더 URL 관례를 그대로
    # 이어받는다 - 실 파일이 없는 문서에 대한 안정적인 provenance/idempotency 키.
    return f"hf-dataset://{source}/{original_id}"


def run_bulk_ingestion(
    source: str,
    db,  # noqa: ANN001 - sqlalchemy.orm.Session, 순환 import 피하려고 타입힌트 생략
    *,
    limit: int | None = None,
    dry_run: bool = True,
    batch_size: int = 50,
    deduplicator: Deduplicator | None = None,
    providers: list[EmbeddingProvider] | None = None,
    shuffle_seed: int | None = None,
) -> BulkIngestionResult:
    """`deduplicator`를 안 넘기면 이 호출 안에서만 중복을 잡는다. 여러 데이터셋에
    걸친 중복까지 잡으려면(신뢰도 높은 데이터셋을 먼저 처리한 뒤 그 결과로 seed한)
    `Deduplicator`를 호출부(scripts/rag_ingest.py)가 넘겨야 한다 - 로컬 전처리
    스크립트(scripts/rag_prepare_dataset.py)와 동일한 방식.

    `batch_size`개 문서씩 모아서(청크/문서 생성은 flush만, 커밋 안 함) 임베딩을
    문서 여러 개 분량을 합쳐 한 번에 계산한 뒤 배치 전체를 한 번에 커밋한다 -
    문서 하나마다 임베딩 API를 부르고 커밋하면 대량 처리 시 네트워크 왕복이
    지나치게 많아진다(파일 상단 설명 참고)."""
    adapter = get_adapter(source)
    pipeline_result = run_ingestion_pipeline(
        adapter, limit=limit, deduplicator=deduplicator, shuffle_seed=shuffle_seed
    )

    source_tier_counts: dict[str, int] = {}
    verification_status_counts: dict[str, int] = {}
    for record in pipeline_result.records:
        tier = record.document_metadata.get("source_tier")
        if tier is not None:
            key = str(tier)
            source_tier_counts[key] = source_tier_counts.get(key, 0) + 1
        status = record.document_metadata.get("verification_status")
        if status is not None:
            verification_status_counts[status] = verification_status_counts.get(status, 0) + 1

    result = BulkIngestionResult(
        source=pipeline_result.source,
        raw_count=pipeline_result.raw_count,
        cleaned_count=pipeline_result.cleaned_count,
        duplicate_count=pipeline_result.duplicate_count,
        chunk_count=pipeline_result.chunk_count,
        dry_run=dry_run,
        filter_stats=pipeline_result.filter_stats,
        source_tier_counts=source_tier_counts,
        verification_status_counts=verification_status_counts,
        shuffle_seed=shuffle_seed,
    )

    admin_repo = AdminDocumentRepository(db)
    chunk_repo = DocumentChunkRepository(db)
    providers = providers if providers is not None else get_default_rag_embedding_providers()

    # idempotency 확인을 레코드당 1번씩 하면(문서 수천~수만 개 기준) 그 자체가
    # 병목이 된다 - 실제로 문서 50개에 배치 임베딩까지 붙여도 107초가 걸렸는데
    # 대부분 이 확인 때문이었다. IN 쿼리 몇 번으로 한꺼번에 확인한다.
    _url_batch = 1000
    all_urls = [
        _synthetic_url(record.normalized.source, record.normalized.original_id)
        for record in pipeline_result.records
    ]
    existing_urls: set[str] = set()
    for start in range(0, len(all_urls), _url_batch):
        existing_urls |= admin_repo.find_existing_urls(all_urls[start : start + _url_batch])

    pending: list[tuple[AdminDocuments, list[DocumentChunks]]] = []
    pending_urls: list[str] = []
    pending_normalized: list[NormalizedRecord] = []

    def flush_batch() -> None:
        if not pending:
            return
        all_chunks = [chunk for _, chunks in pending for chunk in chunks]
        all_texts = [chunk.chunk_text for chunk in all_chunks]
        try:
            for provider in providers:
                vectors = provider.embed_texts(all_texts)
                for chunk, vector in zip(all_chunks, vectors, strict=True):
                    chunk_repo.add_embeddings(chunk.id, provider.name, provider.dimension, vector, commit=False)
            db.commit()
            for _, chunks in pending:
                result.documents_ingested += 1
                result.chunks_ingested += len(chunks)
            result.committed_records.extend(pending_normalized)
        except Exception:
            logger.exception("run_bulk_ingestion: 배치 임베딩/저장 실패 (문서 %d개)", len(pending))
            db.rollback()
            result.failed += len(pending)
            result.errors.extend(pending_urls)
        pending.clear()
        pending_urls.clear()
        pending_normalized.clear()

    for i, (record, url) in enumerate(zip(pipeline_result.records, all_urls, strict=True), start=1):
        if url in existing_urls:
            result.skipped_existing += 1
            # 이미 이전 실행에서 Neon에 durable하게 커밋된 것이 확인된 경우라
            # committed_records에 포함해도 안전하다(오히려 빠뜨리면 다음 실행이
            # 다시 임베딩 API를 부르지는 않지만 dedup 인덱스가 이 내용을 못
            # 잡아 낭비가 생길 수 있다).
            result.committed_records.append(record.normalized)
            continue

        if dry_run:
            continue

        try:
            doc = admin_repo.create(
                original_file_url=url, extracted_text=record.normalized.content, commit=False
            )
            chunks = chunk_repo.create_chunks(
                doc.id,
                [{"chunk_index": c.index, "chunk_text": c.text} for c in record.chunks],
                metadata=record.document_metadata,
                commit=False,
            )
            pending.append((doc, chunks))
            pending_urls.append(url)
            pending_normalized.append(record.normalized)
        except Exception:
            logger.exception("run_bulk_ingestion: 문서/청크 생성 실패 url=%s", url)
            db.rollback()
            result.failed += 1
            result.errors.append(url)
            continue

        if len(pending) >= batch_size:
            flush_batch()
            logger.info(
                "run_bulk_ingestion 진행: %s %d/%d 문서, %d개 청크 저장됨",
                source, i, len(pipeline_result.records), result.chunks_ingested,
            )

    flush_batch()  # 마지막 남은 배치(batch_size로 안 나누어떨어지는 나머지)
    return result


def print_report(result: BulkIngestionResult) -> None:
    """message(5) 25번 섹션이 요구하는 로그 형식."""
    print(f"Dataset: {result.source}")
    print(f"Raw: {result.raw_count}")
    print(f"After cleaning: {result.cleaned_count}")
    print(f"After deduplication: {result.cleaned_count}")
    print(f"Documents: {result.cleaned_count}")
    print(f"Chunks: {result.chunk_count}")
    if result.dry_run:
        print("Jina embeddings: skipped(dry-run)")
        print("BGE embeddings: skipped(dry-run)")
        print(f"Inserted: skipped(dry-run), would-skip-existing={result.skipped_existing}")
    else:
        print(f"Jina embeddings: {result.chunks_ingested}")
        print(f"BGE embeddings: {result.chunks_ingested}")
        print(f"Inserted: {result.chunks_ingested}")
    print(f"Skipped (already ingested): {result.skipped_existing}")
    print(f"Failed: {result.failed}")
    if result.shuffle_seed is not None:
        print(f"shuffle_seed: {result.shuffle_seed}")
    if result.filter_stats:
        print("Filtered:")
        for key, count in sorted(result.filter_stats.items()):
            print(f"  - {key}: {count}")
    if result.source_tier_counts:
        print("source_tier:")
        for tier, count in sorted(result.source_tier_counts.items()):
            print(f"  - tier {tier}: {count}")
    if result.verification_status_counts:
        print("verification_status:")
        for status, count in sorted(result.verification_status_counts.items()):
            print(f"  - {status}: {count}")
