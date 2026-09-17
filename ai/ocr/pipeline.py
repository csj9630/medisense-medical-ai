"""Image/PDF/Office/Text/ZIP 문서를 하나의 순서로 처리하는 Pipeline입니다."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from .contracts import (
    ExtractedDocument,
    OcrDocumentInput,
    OcrDocumentResult,
    OcrEngine,
    OcrLine,
    OcrProcessingConfig,
    ProgressCallback,
    ValidatedDocument,
)
from .engine import get_paddle_ocr_service
from .errors import DocumentProcessingError
from .extractors.archive import process_zip_document
from .extractors.office import OfficeDocumentParser, process_office_document
from .extractors.pdf import process_pdf_document
from .extractors.structured_text import process_structured_text_document
from .postprocessing import clean_document_text
from .preprocessing import is_pdf, preprocess_image
from .validation import validate_document

logger = logging.getLogger(__name__)

DEFAULT_OCR_CONFIG = OcrProcessingConfig(
    max_file_bytes=20 * 1024 * 1024,
    max_pdf_pages=50,
    native_text_min_chars=20,
    significant_image_area_ratio=0.03,
    pdf_render_dpi=200,
    max_image_side=2400,
    max_image_pixels=40_000_000,
    paddle_device="cpu",
    paddle_language="korean",
)


@dataclass(frozen=True)
class OcrResult:
    """기존 ``run_ocr`` 호출자가 사용하던 축약 결과 계약입니다."""

    text: str
    lines: list[OcrLine] = field(default_factory=list)
    min_confidence: float = 0.5


def analyze_document(
    document: OcrDocumentInput,
    config: OcrProcessingConfig,
    progress_callback: ProgressCallback | None = None,
    *,
    ocr_service_factory: Callable[[], OcrEngine] | None = None,
    office_parser: OfficeDocumentParser | None = None,
) -> OcrDocumentResult:
    """입력 → 검증 → 형식별 추출 → 원문 보존 → 정제 → 결과 순서를 관리합니다."""

    logger.info("OCR 문서 처리 시작: bytes=%d", len(document.content))

    # 1. Bytes 입력의 파일명, 크기, MIME과 실제 Binary 구조를 검증합니다.
    _report_progress(progress_callback, "validating", 8, "업로드 파일을 검증하고 있습니다.")
    validated = validate_document(document, config)
    _report_progress(progress_callback, "validating", 15, "파일 검증이 완료되었습니다.")

    # 2. 모든 형식의 Image OCR이 같은 지연 로딩 Paddle Engine을 사용하게 합니다.
    engine_factory = ocr_service_factory or (
        lambda: get_paddle_ocr_service(
            config.paddle_device,
            config.paddle_language,
            config.min_confidence,
        )
    )

    # 3. 형식별 추출기는 결과를 공통 ExtractedDocument로 이 함수에 돌려줍니다.
    _report_progress(progress_callback, "analyzing", 20, "문서 구조를 분석하고 있습니다.")
    extracted = _extract_document(
        validated,
        config,
        engine_factory,
        progress_callback,
        office_parser,
    )
    _report_progress(progress_callback, "merging", 82, "문서 추출 결과를 통합했습니다.")

    # 4. 추출 원문은 별도 보존하고 사용자 표시·후속 처리용 Text만 최소 정제합니다.
    _report_progress(progress_callback, "cleaning", 86, "추출 텍스트를 정제하고 있습니다.")
    raw_text = extracted.raw_text if extracted.raw_text is not None else extracted.text
    cleaned_text = clean_document_text(extracted.text)
    _report_progress(progress_callback, "cleaning", 90, "텍스트 정제가 완료되었습니다.")

    # 5. Line, Confidence, 경고와 문서 Meta를 손실 없이 공통 결과로 반환합니다.
    result = OcrDocumentResult(
        raw_text=raw_text,
        cleaned_text=cleaned_text,
        lines=extracted.lines,
        page_count=extracted.page_count,
        document_type=extracted.document_type,
        ocr_image_count=extracted.ocr_image_count,
        average_confidence=extracted.average_confidence,
        warnings=extracted.warnings,
    )
    logger.info(
        "OCR 문서 처리 완료: type=%s pages=%s ocr_images=%d",
        result.document_type,
        result.page_count,
        result.ocr_image_count,
    )
    return result


def _extract_document(
    document: ValidatedDocument,
    config: OcrProcessingConfig,
    ocr_service_factory: Callable[[], OcrEngine],
    progress_callback: ProgressCallback | None,
    office_parser: OfficeDocumentParser | None,
) -> ExtractedDocument:
    if document.file_type == "image":
        return _process_image_document(
            document,
            config,
            ocr_service_factory,
            progress_callback,
        )
    if document.file_type == "pdf":
        return process_pdf_document(
            document.content,
            config,
            ocr_service_factory,
            progress_callback,
        )
    if document.file_type in {"json", "jsonl", "csv", "txt"}:
        _report_progress(
            progress_callback,
            "extracting",
            80,
            "Text 기반 문서를 직접 추출했습니다.",
        )
        return process_structured_text_document(document)
    if document.file_type == "zip":
        return process_zip_document(
            document,
            config,
            lambda member, callback: analyze_document(
                member,
                config,
                callback,
                ocr_service_factory=ocr_service_factory,
                office_parser=office_parser,
            ),
            progress_callback,
        )
    return process_office_document(
        document,
        config,
        ocr_service_factory,
        progress_callback,
        office_parser,
    )


def _process_image_document(
    document: ValidatedDocument,
    config: OcrProcessingConfig,
    ocr_service_factory: Callable[[], OcrEngine],
    progress_callback: ProgressCallback | None,
) -> ExtractedDocument:
    """일반 Image를 공통 전처리와 단일 Paddle Engine으로 처리합니다."""

    _report_progress(progress_callback, "preprocessing", 28, "OCR용 이미지를 전처리하고 있습니다.")
    processed_image = preprocess_image(
        document.content,
        config.max_image_side,
        config.max_image_pixels,
        enable_denoise=config.enable_denoise,
        enable_deskew=config.enable_deskew,
    )
    _report_progress(progress_callback, "loading_model", 35, "PaddleOCR 모델을 준비하고 있습니다.")
    ocr_result = ocr_service_factory().extract_text(processed_image)
    _report_progress(progress_callback, "extracting", 80, "이미지 OCR이 완료되었습니다.")

    warnings = []
    if not ocr_result.text:
        warnings.append("이미지에서 인식 가능한 텍스트를 찾지 못했습니다.")
    return ExtractedDocument(
        text=ocr_result.text,
        page_count=1,
        document_type="image",
        ocr_image_count=1,
        average_confidence=ocr_result.confidence,
        warnings=warnings,
        lines=ocr_result.lines,
        raw_text=ocr_result.raw_text or ocr_result.text,
    )


def run_ocr(image_bytes: bytes, min_confidence: float = 0.5) -> OcrResult:
    """기존 공개 Import를 새 ``analyze_document``로 연결하는 호환 Wrapper입니다."""

    file_name, content_type = _infer_legacy_input(image_bytes)
    config = replace(DEFAULT_OCR_CONFIG, min_confidence=min_confidence)
    result = analyze_document(
        OcrDocumentInput(
            file_name=file_name,
            content_type=content_type,
            content=image_bytes,
        ),
        config,
    )
    return OcrResult(
        text=result.cleaned_text,
        lines=result.lines,
        min_confidence=min_confidence,
    )


def _infer_legacy_input(content: bytes) -> tuple[str, str]:
    if is_pdf(content):
        return "document.pdf", "application/pdf"

    try:
        with Image.open(BytesIO(content)) as image:
            image_format = (image.format or "").upper()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise DocumentProcessingError("이미지 또는 PDF를 읽지 못했습니다.") from exc

    if image_format == "PNG":
        return "image.png", "image/png"
    if image_format == "JPEG":
        return "image.jpg", "image/jpeg"
    raise DocumentProcessingError("PNG, JPG 또는 PDF만 run_ocr로 처리할 수 있습니다.")


def _report_progress(
    callback: ProgressCallback | None,
    stage: str,
    progress: int,
    message: str,
) -> None:
    if callback is not None:
        callback(stage, max(0, min(progress, 99)), message)
