"""FastAPI UploadFile과 공통 ai.ocr Core 사이의 Backend Adapter입니다."""

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path

from fastapi import UploadFile

from ai.ocr import (
    OcrDocumentInput,
    OcrDocumentResult,
    OcrProcessingConfig,
    analyze_document,
)
from ai.ocr.contracts import ProgressCallback
from ai.ocr.errors import DocumentValidationError
from app.core.config import settings
from app.schemas.admin import OcrDocumentResponse
from app.services.ocr_chunk_service import create_chunks

from typing import Literal

logger = logging.getLogger(__name__)

DOCUMENT_TYPE_LABELS = {
    "image": "이미지",
    "digital_pdf": "디지털 PDF",
    "hybrid_pdf": "Hybrid PDF",
    "scanned_pdf": "스캔 PDF",
    "docx_direct": "DOCX 직접 추출",
    "pptx_direct": "PPTX 직접 추출",
    "json_direct": "JSON 직접 추출",
    "jsonl_direct": "JSONL 직접 추출",
    "csv_direct": "CSV 직접 추출",
    "txt_direct": "TXT 직접 추출",
    "zip_archive": "ZIP 압축 문서",
    "web_page": "웹페이지",
}

CoreAnalyzer = Callable[
    [OcrDocumentInput, OcrProcessingConfig, ProgressCallback | None],
    OcrDocumentResult,
]


class OcrWorkflowService:
    """파일 읽기 → Core 실행 → Chunk → Admin 응답 순서를 관리합니다."""

    def __init__(
        self,
        config: OcrProcessingConfig,
        core_analyzer: CoreAnalyzer = analyze_document,
    ) -> None:
        self.config = config
        self.core_analyzer = core_analyzer

    async def analyze_upload(
        self,
        file: UploadFile,
        progress_callback: ProgressCallback | None = None,
    ) -> OcrDocumentResult:
        """UploadFile을 제한 크기까지만 읽고 CPU OCR을 Worker Thread에서 실행합니다."""

        # 1. 선언된 Content-Length를 신뢰하지 않고 제한보다 한 Byte 더 읽습니다.
        content = await file.read(self.config.max_file_bytes + 1)
        document = OcrDocumentInput(
            file_name=file.filename or "",
            content_type=file.content_type or "application/octet-stream",
            content=content,
        )

        # 2. 동기 CPU OCR이 FastAPI Event Loop를 막지 않도록 Thread 경계를 둡니다.
        return await asyncio.to_thread(
            self.core_analyzer,
            document,
            self.config,
            progress_callback,
        )

    async def process_document(
        self,
        file: UploadFile,
        chunk_size: int,
        overlap: int,
        progress_callback: ProgressCallback | None = None,
    ) -> OcrDocumentResponse:
        """공통 OCR 결과에 Admin 전용 Chunk와 Readiness를 추가합니다."""

        logger.info("Admin OCR Workflow 시작")

        # 1. Admin 문자 Chunk가 정지하거나 역행하지 않도록 옵션을 검증합니다.
        validate_chunk_options(chunk_size, overlap)

        # 2. 실제 문서 검증과 추출은 서비스 API와 같은 ai.ocr Core에 맡깁니다.
        result = await self.analyze_upload(file, progress_callback)

        # 3. OCR Core 밖에서 관리자 검토용 문자 Chunk를 생성합니다.
        _report_progress(progress_callback, "chunking", 93, "RAG 검토용 Chunk를 생성하고 있습니다.")
        chunks = create_chunks(result.cleaned_text, chunk_size, overlap)
        _report_progress(
            progress_callback,
            "chunking",
            97,
            f"Chunk {len(chunks)}개를 생성했습니다.",
        )

        # 4. 기존 Admin Frontend의 camelCase Response 계약에 맞게 결과를 조립합니다.
        response = build_admin_ocr_response(
            file_name=file.filename or "",
            result=result,
            chunks=chunks,
        )
        _report_progress(progress_callback, "finalizing", 99, "분석 결과를 구성했습니다.")
        logger.info("Admin OCR Workflow 완료: chunks=%d", len(chunks))
        return response


def validate_chunk_options(chunk_size: int, overlap: int) -> None:
    if overlap >= chunk_size:
        raise DocumentValidationError("Overlap은 Chunk Size보다 작아야 합니다.")


def build_admin_ocr_response(
    *,
    file_name: str,
    result: OcrDocumentResult,
    chunks: list[str],
    source_type: Literal["file", "url"] = "file",
    source_url: str | None = None,
) -> OcrDocumentResponse:
    """Framework 독립 Core 결과를 기존 Admin Response로 변환합니다."""

    safe_file_name = (
        file_name.strip()[:255]
        if source_type == "url"
        else Path(file_name.replace("\\", "/")).name
    )
    confidence_percent = round(result.average_confidence * 100, 1)
    notes = [
        f"문서 유형: {DOCUMENT_TYPE_LABELS.get(result.document_type, result.document_type)}",
        f"PaddleOCR 처리 이미지: {result.ocr_image_count}개",
        *result.warnings,
    ]
    if result.document_type.startswith("docx"):
        notes.insert(0, "원본 형식: DOCX")
    elif result.document_type.startswith("pptx"):
        notes.insert(0, "원본 형식: PPTX")
    elif result.document_type.endswith("_direct"):
        notes.insert(0, f"원본 형식: {result.document_type.removesuffix('_direct').upper()}")
    elif result.document_type == "zip_archive":
        notes.insert(0, "원본 형식: ZIP")

    review_warning_keywords = (
        "실패",
        "제외",
        "건너뛰",
        "읽지 못",
        "완전하게",
        "다를 수",
        "만 추출",
    )
    needs_review = (
        not result.cleaned_text
        or confidence_percent < 80
        or any(
            keyword in warning
            for warning in result.warnings
            for keyword in review_warning_keywords
        )
    )
    return OcrDocumentResponse(
        documentName=safe_file_name,
        pageCount=result.page_count,
        characterCount=len(result.cleaned_text),
        estimatedChunks=len(chunks),
        confidence=confidence_percent,
        extractedText=result.cleaned_text,
        chunks=chunks,
        readiness="review" if needs_review else "ready",
        notes=notes,
        sourceType=source_type,
        sourceUrl=source_url,
    )


def _build_default_config() -> OcrProcessingConfig:
    return OcrProcessingConfig(
        max_file_bytes=settings.ocr_inline_file_size_mb * 1024 * 1024,
        max_pdf_pages=settings.ocr_max_pdf_pages,
        native_text_min_chars=settings.ocr_native_text_min_chars,
        significant_image_area_ratio=settings.ocr_significant_image_area_ratio,
        pdf_render_dpi=settings.ocr_pdf_render_dpi,
        max_image_side=settings.ocr_max_image_side,
        max_image_pixels=settings.ocr_max_image_pixels,
        paddle_device=settings.ocr_paddle_device,
        paddle_language=settings.ocr_paddle_language,
        max_office_uncompressed_bytes=(
            settings.ocr_max_office_uncompressed_size_mb * 1024 * 1024
        ),
        max_office_archive_entries=settings.ocr_max_office_archive_entries,
        min_confidence=settings.ocr_min_confidence,
        enable_denoise=settings.ocr_enable_denoise,
        enable_deskew=settings.ocr_enable_deskew,
    )


def _report_progress(
    callback: ProgressCallback | None,
    stage: str,
    progress: int,
    message: str,
) -> None:
    if callback is not None:
        callback(stage, max(0, min(progress, 99)), message)


ocr_workflow_service = OcrWorkflowService(_build_default_config())


async def analyze_uploaded_document(
    file: UploadFile,
    progress_callback: ProgressCallback | None = None,
) -> OcrDocumentResult:
    """서비스 문서 OCR Endpoint가 호출하는 공통 Core Adapter입니다."""

    return await ocr_workflow_service.analyze_upload(file, progress_callback)


async def process_document(
    file: UploadFile,
    chunk_size: int,
    overlap: int,
    progress_callback: ProgressCallback | None = None,
) -> OcrDocumentResponse:
    """Admin Analyze/Job이 유지하는 기존 Processor Callable 계약입니다."""

    return await ocr_workflow_service.process_document(
        file=file,
        chunk_size=chunk_size,
        overlap=overlap,
        progress_callback=progress_callback,
    )
