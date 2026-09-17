"""완료된 OCR Job의 Chunk를 Embedding과 함께 Neon에 저장합니다."""

import hashlib
import logging
from collections.abc import Iterator
from typing import Protocol
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.document_chunk import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository, SavedDocument
from app.schemas.admin import OcrVectorSaveRequest, OcrVectorSaveResponse
from app.services.embedding_service import (
    EmbeddingBatch,
    EmbeddingService,
    EmbeddingValidationError,
    embedding_service,
)
from app.services.ocr_job_service import OcrJobManager, ocr_job_manager
from app.services.large_document_service import iter_chunk_artifact
from app.services.r2_storage import R2StorageService, rag_r2_storage
from ai.rag.ingestion.cleaning import clean_content
from ai.rag.ingestion.quality import detect_needs_review

logger = logging.getLogger(__name__)

NEON_VECTOR_DIMENSION = 1024


class OcrSaveValidationError(Exception):
    """OCR 결과가 저장 가능한 상태가 아닐 때 발생합니다."""


class DocumentSaver(Protocol):
    def save_with_chunks(
        self,
        *,
        original_file_url: str,
        extracted_text: str,
        chunks: list[str],
        embeddings_by_provider: dict[str, list[list[float]]],
        chunk_metadata: dict | None = None,
    ) -> SavedDocument: ...


def _build_chunk_metadata(result) -> dict:
    """관리자 업로드 청크가 답변의 출처 표시(source)에 나올 수 있게 자동으로
    채운다 - 관리자가 따로 입력할 UI 없이, OCR Job이 이미 알고 있는 정보(웹
    URL로 수집했는지, 파일 업로드인지)만으로 정한다.

    2026-09-04: source_tier(신뢰도 부스트)는 일부러 안 채운다 - "관리자가 직접
    골라서 넣었다"는 사실이 "품질이 검증됐다"는 뜻은 아니다(실제로 개발자가
    테스트 삼아 올린 문서가 이 경로로 들어왔다가 나중에 삭제된 적이 있음).
    URL이든 파일이든 우리가 실제로 검증한 적 없는 출처라 source_tier 없이
    중립(1.0배, 부스트도 페널티도 없음)으로 둔다 - rag_search_service.
    _boost_multiplier가 없는 tier는 1.0으로 처리하므로 안전하다. 신뢰도를
    실제로 매기려면 관리자가 업로드 시점에 직접 선택하게 하는 UI가 필요한데,
    그건 아직 없다(후속 과제).

    2026-09-07: needs_review도 HF/KDCA 데이터와 똑같이 채운다
    (ai/rag/ingestion/quality.detect_needs_review - 용량/처방/응급 등 위험
    키워드가 있으면 표시만 해두고 내용은 안 고침). ai/rag/ingestion/
    pipeline.py의 build_document_metadata()도 문서 전체 content 한 번만 보고
    판단해서 그 문서의 모든 청크에 같은 값을 적용하므로, 여기서도 문서 전체
    텍스트(extracted_text) 한 번만 보고 같은 방식으로 적용한다 - 이러면
    scripts/report_needs_review.py가 관리자 업로드분까지 그대로 같이 집계한다.
    (한계: 8GB 스테이지드 업로드는 extracted_text가 미리보기 앞부분만이라,
    그 뒤에만 나오는 위험 키워드는 못 잡는다 - 문서 전체를 메모리에 올리지
    않는 스트리밍 설계상 트레이드오프다.)"""
    extracted_text = getattr(result, "extracted_text", "") or ""
    metadata: dict = {"needs_review": detect_needs_review(extracted_text)}

    source_type = getattr(result, "source_type", None)
    if source_type == "url":
        source_url = getattr(result, "source_url", None)
        if source_url:
            metadata["source"] = source_url
        return metadata
    document_name = getattr(result, "document_name", None)
    if document_name:
        metadata["source"] = document_name
    return metadata


def _filter_clean_chunks(chunks: list[str]) -> tuple[list[str], int]:
    """임베딩 직전에 청크 하나하나를 ai/rag/ingestion과 같은 정제 게이트
    (clean_content - 깨진 유니코드/HTML 잔재/프롬프트 템플릿 유출/특수문자
    과다 비율을 통째로 거부)에 통과시킨다. 문서 전체가 아니라 청크 단위로
    적용하는 이유: 관리자 업로드(특히 8GB 스트리밍 경로)는 문서 전체를
    메모리에 모아두지 않으므로, "문서 전체를 보고 거부/통과"를 판단할 수
    없다 - 이미 만들어진 작은 청크 하나씩만 검사하면 스트리밍 구조를
    그대로 유지하면서도 같은 품질 기준을 적용할 수 있다. (2026-09-04)"""
    cleaned: list[str] = []
    rejected = 0
    for chunk in chunks:
        result = clean_content(chunk)
        if result is None:
            rejected += 1
            continue
        cleaned.append(result)
    return cleaned, rejected


def _filter_duplicate_chunks(chunks: list[str], db: Session) -> tuple[list[str], int]:
    """이미 document_chunks에 완전히 같은 텍스트로 있는 청크는 저장하지 않는다
    (2026-09-07) - 같은 파일을 실수로 두 번 올리거나, 이미 HF/KDCA 데이터셋으로
    들어가 있는 내용과 겹치는 파일을 올려도 중복 저장되지 않는다. 정제
    필터(_filter_clean_chunks) 다음 단계로 둔다 - 정제로 빠질 청크까지
    중복 조회할 필요는 없어서다. 매 요청마다 실시간 DB 조회라 여러 관리자가
    동시에 업로드해도(각자 독립적인 SELECT) 파일 기반 인덱스 같은 동시성
    문제가 없다(document_chunk.py의 find_existing_chunk_texts 참고).

    DB 조회와 별개로, 이번에 저장하려는 chunks 리스트 "안에서" 완전히 같은
    텍스트가 반복되는 경우(예: 페이지마다 반복되는 머리말/꼬리말이 청크
    하나씩으로 뽑힌 경우)도 같은 방식으로 걸러낸다 - find_existing_chunk_texts는
    DB에 이미 있는 것만 알려주므로, 이 배치 안에서 처음 등장한 것끼리는 서로를
    걸러주지 못하기 때문이다."""
    if not chunks:
        return chunks, 0
    existing = DocumentChunkRepository(db).find_existing_chunk_texts(chunks)
    deduped: list[str] = []
    seen_in_batch: set[str] = set()
    for chunk in chunks:
        if chunk in existing or chunk in seen_in_batch:
            continue
        seen_in_batch.add(chunk)
        deduped.append(chunk)
    return deduped, len(chunks) - len(deduped)


async def save_ocr_result_with_embeddings(
    request: OcrVectorSaveRequest,
    db: Session,
    *,
    job_manager: OcrJobManager = ocr_job_manager,
    embedder: EmbeddingService = embedding_service,
    repository: DocumentSaver | None = None,
    storage: R2StorageService = rag_r2_storage,
) -> OcrVectorSaveResponse:
    """OCR 결과 조회 → Embedding → 문서·Chunk Transaction 저장을 관리합니다."""

    job = job_manager.get_job(request.job_id)
    if job.status != "completed" or job.result is None:
        raise OcrSaveValidationError("완료된 OCR Job만 VectorDB에 저장할 수 있습니다.")
    if not job.result.chunks:
        raise OcrSaveValidationError("저장할 OCR Chunk가 없습니다.")

    document_repository = repository or DocumentRepository(db)
    chunk_metadata = _build_chunk_metadata(job.result)
    if job.result.chunk_artifact_key:
        return await _save_staged_result(
            result=job.result,
            embedder=embedder,
            repository=document_repository,
            storage=storage,
            chunk_metadata=chunk_metadata,
            db=db,
        )

    logger.info(
        "[OCR SAVE] document save start: job_id=%s chunks=%d",
        request.job_id,
        len(job.result.chunks),
    )
    chunks, rejected_count = _filter_clean_chunks(job.result.chunks)
    chunks, duplicate_count = _filter_duplicate_chunks(chunks, db)
    if not chunks:
        raise OcrSaveValidationError("정제/중복 제외 후 저장할 OCR Chunk가 남지 않았습니다.")

    embeddings = await embedder.embed_chunks(chunks)
    _validate_embeddings_before_storage(
        chunks=chunks,
        embeddings=embeddings,
        configured_dimension=embedder.dimension,
    )

    saved = document_repository.save_with_chunks(
        original_file_url=(
            job.result.source_url
            if job.result.source_type == "url" and job.result.source_url
            else _build_job_file_reference(request.job_id, job.result.document_name)
        ),
        extracted_text=job.result.extracted_text,
        chunks=chunks,
        embeddings_by_provider=embeddings.vectors_by_provider,
        chunk_metadata=chunk_metadata,
    )
    return OcrVectorSaveResponse(
        message=_build_save_message(saved.chunk_count, rejected_count, duplicate_count),
        documentId=saved.document_id,
        chunkCount=saved.chunk_count,
        embeddingProvider=embedder.provider,
        embeddingDimension=embedder.dimension,
        embeddingModel=embedder.model,
    )


async def _save_staged_result(
    *,
    result,
    embedder: EmbeddingService,
    repository,
    storage: R2StorageService,
    db: Session,
    chunk_metadata: dict | None = None,
) -> OcrVectorSaveResponse:
    artifact_key = result.chunk_artifact_key
    if not artifact_key or not result.original_object_key:
        raise OcrSaveValidationError("대용량 OCR 저장 정보가 올바르지 않습니다.")

    document_id = repository.begin_staged_save(
        original_file_url=_build_r2_file_reference(result.original_object_key),
        extracted_text=result.extracted_text,
    )
    chunk_count = 0
    rejected_total = 0
    duplicate_total = 0
    try:
        for raw_chunks in _batched(
            iter_chunk_artifact(artifact_key, storage),
            settings.embedding_batch_size,
        ):
            chunks, rejected = _filter_clean_chunks(raw_chunks)
            rejected_total += rejected
            chunks, duplicate = _filter_duplicate_chunks(chunks, db)
            duplicate_total += duplicate
            if not chunks:
                continue  # 이 배치가 전부 정제/중복 기준에 걸러졌으면 임베딩 호출 자체를 건너뛴다
            embeddings = await embedder.embed_chunks(chunks)
            _validate_embeddings_before_storage(
                chunks=chunks,
                embeddings=embeddings,
                configured_dimension=embedder.dimension,
            )
            repository.append_staged_chunks(
                document_id=document_id,
                start_index=chunk_count,
                chunks=chunks,
                embeddings_by_provider=embeddings.vectors_by_provider,
                chunk_metadata=chunk_metadata,
            )
            chunk_count += len(chunks)
        if chunk_count == 0:
            raise OcrSaveValidationError("정제/중복 제외 후 저장할 OCR Chunk가 남지 않았습니다.")
        saved = repository.finish_staged_save(document_id, chunk_count)
    except Exception:
        try:
            repository.abort_staged_save(document_id)
        except Exception:
            logger.exception("실패한 대용량 OCR 문서 정리 실패: document_id=%s", document_id)
        raise

    try:
        storage.delete_object(artifact_key)
    except Exception:
        logger.exception("저장 완료 후 Chunk artifact 정리 실패: key=%s", artifact_key)

    return OcrVectorSaveResponse(
        message=_build_save_message(saved.chunk_count, rejected_total, duplicate_total),
        documentId=saved.document_id,
        chunkCount=saved.chunk_count,
        embeddingProvider=embedder.provider,
        embeddingDimension=embedder.dimension,
        embeddingModel=embedder.model,
    )


def _build_save_message(saved_chunk_count: int, rejected_count: int, duplicate_count: int = 0) -> str:
    message = f"OCR 문서와 Chunk {saved_chunk_count}개를 VectorDB에 저장했습니다."
    notes = []
    if rejected_count:
        notes.append(f"품질 기준으로 {rejected_count}개 청크는 제외됨")
    if duplicate_count:
        notes.append(f"중복으로 {duplicate_count}개 청크는 제외됨")
    if notes:
        message += f" ({', '.join(notes)})"
    return message


def _batched(values: Iterator[str], batch_size: int) -> Iterator[list[str]]:
    batch: list[str] = []
    for value in values:
        batch.append(value)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def _build_r2_file_reference(object_key: str) -> str:
    reference = f"r2:///{object_key}"
    if len(reference) <= 500:
        return reference
    return f"r2:///admin-rag-uploads/{hashlib.sha256(object_key.encode()).hexdigest()}"


def _build_job_file_reference(job_id: str, document_name: str) -> str:
    """원본 저장소가 생기기 전까지 영구 파일 URL과 구분되는 Job 추적값을 기록합니다."""

    reference = f"ocr-job://{job_id}/{quote(document_name, safe='._-')}"
    if len(reference) <= 500:
        return reference
    name_digest = hashlib.sha256(document_name.encode("utf-8")).hexdigest()
    return f"ocr-job://{job_id}/{name_digest}"


def _validate_embeddings_before_storage(
    *,
    chunks: list[str],
    embeddings: EmbeddingBatch,
    configured_dimension: int,
) -> None:
    """Neon 저장 직전에 Jina/BGE 실제 Vector가 1024차원 계약과 같은지 재검증합니다."""

    if configured_dimension != NEON_VECTOR_DIMENSION:
        raise EmbeddingValidationError(
            "Embedding 설정 차원은 Jina/BGE 실제 Vector 계약인 "
            f"VECTOR({NEON_VECTOR_DIMENSION})와 같아야 합니다. "
            f"현재 설정: {configured_dimension}"
        )
    if len(embeddings.vectors_by_provider) != 2:
        raise EmbeddingValidationError("Jina/BGE 두 Provider의 Embedding이 모두 필요합니다.")
    for provider_name, vectors in embeddings.vectors_by_provider.items():
        if len(chunks) != len(vectors):
            raise EmbeddingValidationError(
                f"OCR Chunk는 {len(chunks)}개지만 {provider_name} Vector는 {len(vectors)}개입니다."
            )
        for index, vector in enumerate(vectors):
            if len(vector) != NEON_VECTOR_DIMENSION:
                raise EmbeddingValidationError(
                    f"{provider_name} Chunk {index}의 Embedding 차원은 {len(vector)}입니다. "
                    f"Neon 저장에는 정확히 {NEON_VECTOR_DIMENSION}차원이 필요합니다."
                )
