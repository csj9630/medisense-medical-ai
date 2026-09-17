"""웹 URL 수집 결과를 기존 Admin OCR 응답과 Chunk 계약으로 변환합니다."""

import asyncio
import logging

from ai.ocr.contracts import OcrProcessingConfig, ProgressCallback
from ai.ocr.engine import get_paddle_ocr_service
from ai.ocr.errors import WebContentTooLargeError, WebUrlValidationError
from ai.ocr.extractors.web import build_web_ocr_result, parse_web_document
from app.core.config import settings
from app.schemas.admin import OcrDocumentResponse
from app.services.ocr_chunk_service import create_chunks
from app.services.ocr_workflow import (
    build_admin_ocr_response,
    ocr_workflow_service,
    validate_chunk_options,
)
from app.services.web_document_fetcher import (
    WebDocumentFetcher,
    WebFetchConfig,
    normalize_web_url,
)

logger = logging.getLogger(__name__)


class WebOcrWorkflowService:
    def __init__(
        self,
        fetcher: WebDocumentFetcher,
        ocr_config: OcrProcessingConfig,
        *,
        max_text_chars: int,
        max_chunks: int,
    ) -> None:
        self.fetcher = fetcher
        self.ocr_config = ocr_config
        self.max_text_chars = max_text_chars
        self.max_chunks = max_chunks

    def validate_url_syntax(self, url: str) -> str:
        return normalize_web_url(url, self.fetcher.config.max_url_length)

    async def process_url(
        self,
        url: str,
        chunk_size: int,
        overlap: int,
        progress_callback: ProgressCallback | None = None,
    ) -> OcrDocumentResponse:
        validate_chunk_options(chunk_size, overlap)
        normalized_url = self.validate_url_syntax(url)
        _report(progress_callback, "fetching", 12, "웹페이지 연결 주소를 검증하고 있습니다.")
        page = await self.fetcher.fetch_page(normalized_url)
        _report(progress_callback, "extracting", 38, "웹페이지 본문과 이미지 목록을 추출하고 있습니다.")
        parsed = await asyncio.to_thread(
            parse_web_document, page.html_text, page.final_url
        )
        if not parsed.text and not parsed.images:
            raise WebUrlValidationError("웹페이지에서 추출할 본문이나 이미지를 찾지 못했습니다.")
        if len(parsed.text) > self.max_text_chars:
            raise WebContentTooLargeError(
                f"웹페이지 본문은 최대 {self.max_text_chars:,}자까지 처리할 수 있습니다."
            )

        _report(progress_callback, "image_ocr", 55, "웹페이지 내부 이미지를 수집하고 있습니다.")
        images, image_warnings = await self.fetcher.fetch_images(parsed.images)
        engine = get_paddle_ocr_service(
            device=self.ocr_config.paddle_device,
            language=self.ocr_config.paddle_language,
            min_confidence=self.ocr_config.min_confidence,
        )
        result = await asyncio.to_thread(
            build_web_ocr_result,
            parsed,
            images,
            self.ocr_config,
            engine,
            image_warnings=image_warnings,
        )
        if not result.cleaned_text:
            raise WebUrlValidationError(
                "웹페이지 본문과 내부 이미지에서 추출 가능한 텍스트를 찾지 못했습니다."
            )
        if len(result.cleaned_text) > self.max_text_chars:
            raise WebContentTooLargeError(
                f"이미지 OCR을 포함한 텍스트는 최대 {self.max_text_chars:,}자까지 처리할 수 있습니다."
            )
        _report(progress_callback, "chunking", 92, "RAG 검색용 Chunk를 생성하고 있습니다.")
        chunks = create_chunks(result.cleaned_text, chunk_size, overlap)
        if len(chunks) > self.max_chunks:
            raise WebContentTooLargeError(
                f"웹 문서는 최대 {self.max_chunks}개 Chunk까지 처리할 수 있습니다."
            )
        response = build_admin_ocr_response(
            file_name=parsed.title,
            result=result,
            chunks=chunks,
            source_type="url",
            source_url=page.final_url,
        )
        _report(progress_callback, "finalizing", 99, "웹페이지 분석 결과를 구성했습니다.")
        logger.info("Admin Web OCR 완료: url=%s chunks=%d", page.final_url, len(chunks))
        return response


def _report(
    callback: ProgressCallback | None,
    stage: str,
    progress: int,
    message: str,
) -> None:
    if callback is not None:
        callback(stage, max(0, min(progress, 99)), message)


web_ocr_workflow_service = WebOcrWorkflowService(
    fetcher=WebDocumentFetcher(
        WebFetchConfig(
            max_url_length=settings.ocr_web_max_url_length,
            max_html_bytes=settings.ocr_web_max_html_size_mb * 1024 * 1024,
            max_redirects=settings.ocr_web_max_redirects,
            connect_timeout_seconds=settings.ocr_web_connect_timeout_seconds,
            read_timeout_seconds=settings.ocr_web_read_timeout_seconds,
            max_images=settings.ocr_web_max_images,
            max_image_bytes=settings.ocr_web_max_image_size_mb * 1024 * 1024,
            max_total_image_bytes=settings.ocr_web_max_total_image_size_mb * 1024 * 1024,
            image_concurrency=settings.ocr_web_image_concurrency,
            max_image_pixels=settings.ocr_max_image_pixels,
        )
    ),
    ocr_config=ocr_workflow_service.config,
    max_text_chars=settings.ocr_web_max_text_chars,
    max_chunks=settings.ocr_web_max_chunks,
)


async def process_web_url(
    url: str,
    chunk_size: int,
    overlap: int,
    progress_callback: ProgressCallback | None = None,
) -> OcrDocumentResponse:
    return await web_ocr_workflow_service.process_url(
        url, chunk_size, overlap, progress_callback
    )
