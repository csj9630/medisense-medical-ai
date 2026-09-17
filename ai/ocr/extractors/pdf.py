"""PDF 구조 분석, Native Text 추출, 필요한 이미지 OCR을 담당합니다."""

import logging
from dataclasses import dataclass, replace
from typing import Callable

import pymupdf

from ..errors import (
    DocumentProcessingError,
    OcrUnavailableError,
)
from ..preprocessing import preprocess_image
from ..contracts import (
    ExtractedDocument,
    OcrEngine,
    OcrLine,
    OcrProcessingConfig,
    ProgressCallback,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PdfPageAnalysis:
    """한 PDF 페이지에서 Native Text와 이미지 존재 여부를 분석한 결과입니다."""

    page_number: int
    native_text: str
    native_character_count: int
    significant_image_count: int
    requires_page_ocr: bool


def process_pdf_document(
    content: bytes,
    config: OcrProcessingConfig,
    ocr_service_factory: Callable[[], OcrEngine],
    progress_callback: ProgressCallback | None = None,
) -> ExtractedDocument:
    """PDF의 페이지별 Native/OCR 처리 순서를 관리하는 중심 함수입니다."""

    try:
        with pymupdf.open(stream=content, filetype="pdf") as document:
            # 1. Native Text 양과 유효 이미지 영역을 기준으로 페이지 구조를 분석합니다.
            analyses = analyze_pdf_structure(document, config)
            _report_progress(
                progress_callback,
                "analyzing",
                25,
                f"PDF {document.page_count}페이지의 구조를 분석했습니다.",
            )
            logger.info(
                "PDF 분석 완료: pages=%d, ocr_targets=%d",
                document.page_count,
                sum(
                    1 if item.requires_page_ocr else item.significant_image_count
                    for item in analyses
                ),
            )

            # 2. 각 페이지를 문서 순서대로 처리하고 결과를 다시 이 중심 함수로 받습니다.
            page_texts: list[str] = []
            raw_page_texts: list[str] = []
            ocr_lines: list[OcrLine] = []
            warnings: list[str] = []
            confidences: list[float] = []
            ocr_image_count = 0
            page_sources: list[str] = []

            total_pages = max(len(analyses), 1)
            for page_index, analysis in enumerate(analyses):
                page_start_progress = 25 + round(page_index / total_pages * 55)
                page_end_progress = 25 + round((page_index + 1) / total_pages * 55)
                page = document.load_page(analysis.page_number - 1)

                _report_progress(
                    progress_callback,
                    "extracting",
                    page_start_progress,
                    f"PDF {analysis.page_number}/{total_pages}페이지를 처리하고 있습니다.",
                )

                if analysis.requires_page_ocr:
                    text, raw_text, page_confidences, page_warnings, page_lines = _process_scanned_page(
                        page,
                        analysis.page_number,
                        config,
                        ocr_service_factory,
                        progress_callback,
                        page_start_progress,
                    )
                    source = "ocr" if text else "empty"
                    ocr_image_count += 1
                elif analysis.significant_image_count:
                    text, raw_text, page_confidences, page_warnings, processed_images, page_lines = (
                        _process_hybrid_page(
                            page,
                            analysis.page_number,
                            config,
                            ocr_service_factory,
                            progress_callback,
                            page_start_progress,
                        )
                    )
                    source = "hybrid"
                    ocr_image_count += processed_images
                else:
                    # 디지털 PDF는 OCR하지 않고 pymupdf4llm의 구조화된 Markdown을 우선 사용합니다.
                    text, native_warning = extract_native_pdf_text(
                        document,
                        analysis.page_number - 1,
                        analysis.native_text,
                    )
                    page_confidences = []
                    page_warnings = [native_warning] if native_warning else []
                    raw_text = text
                    page_lines = []
                    source = "native" if text else "empty"

                _report_progress(
                    progress_callback,
                    "extracting",
                    page_end_progress,
                    f"PDF {analysis.page_number}/{total_pages}페이지 처리를 완료했습니다.",
                )

                page_sources.append(source)
                confidences.extend(page_confidences)
                warnings.extend(page_warnings)
                ocr_lines.extend(page_lines)
                if text:
                    page_texts.append(f"## 페이지 {analysis.page_number}\n\n{text.strip()}")
                else:
                    warnings.append(
                        f"{analysis.page_number}페이지에서 추출 가능한 텍스트가 없습니다."
                    )
                if raw_text:
                    raw_page_texts.append(
                        f"## 페이지 {analysis.page_number}\n\n{raw_text.strip()}"
                    )

            # 3. 페이지 순서를 유지한 통합 텍스트와 문서 유형을 중심 함수로 반환합니다.
            document_type = _classify_document_type(page_sources)
            average_confidence = (
                sum(confidences) / len(confidences)
                if confidences
                else (1.0 if page_texts else 0.0)
            )
            return ExtractedDocument(
                text="\n\n".join(page_texts),
                page_count=document.page_count,
                document_type=document_type,
                ocr_image_count=ocr_image_count,
                average_confidence=average_confidence,
                warnings=warnings,
                lines=ocr_lines,
                raw_text="\n\n".join(raw_page_texts),
            )
    except (OcrUnavailableError, DocumentProcessingError):
        raise
    except (pymupdf.FileDataError, RuntimeError, ValueError) as exc:
        raise DocumentProcessingError("PDF 내용을 추출하는 중 오류가 발생했습니다.") from exc


def analyze_pdf_structure(
    document: pymupdf.Document,
    config: OcrProcessingConfig,
) -> list[PdfPageAnalysis]:
    """페이지별 Native Text와 이미지 면적을 확인해 OCR 경로를 결정합니다."""

    analyses: list[PdfPageAnalysis] = []
    for page_index in range(document.page_count):
        page = document.load_page(page_index)
        native_text = page.get_text("text", sort=True).strip()
        significant_images = _significant_image_blocks(
            page,
            config.significant_image_area_ratio,
        )
        native_character_count = len("".join(native_text.split()))
        analyses.append(
            PdfPageAnalysis(
                page_number=page_index + 1,
                native_text=native_text,
                native_character_count=native_character_count,
                significant_image_count=len(significant_images),
                requires_page_ocr=(
                    native_character_count < config.native_text_min_chars
                ),
            )
        )
    return analyses


def extract_native_pdf_text(
    document: pymupdf.Document,
    page_index: int,
    fallback_text: str,
) -> tuple[str, str | None]:
    """pymupdf4llm으로 Markdown을 만들고 실패하면 PyMuPDF Text로 복구합니다."""

    try:
        import pymupdf4llm

        markdown = pymupdf4llm.to_markdown(
            document,
            pages=[page_index],
            force_text=True,
            ignore_images=True,
            page_separators=False,
            show_progress=False,
        )
        if isinstance(markdown, str) and markdown.strip():
            return markdown.strip(), None
    except Exception:
        logger.warning(
            "pymupdf4llm 추출 실패, PyMuPDF Text로 대체합니다: page=%d",
            page_index + 1,
            exc_info=True,
        )

    return (
        fallback_text.strip(),
        f"{page_index + 1}페이지는 PyMuPDF 기본 텍스트 추출로 대체했습니다.",
    )


def _process_scanned_page(
    page: pymupdf.Page,
    page_number: int,
    config: OcrProcessingConfig,
    ocr_service_factory: Callable[[], OcrEngine],
    progress_callback: ProgressCallback | None,
    progress: int,
) -> tuple[str, str, list[float], list[str], list[OcrLine]]:
    """Native Text가 부족한 페이지 전체를 렌더링해 PaddleOCR로 처리합니다."""

    try:
        pixmap = page.get_pixmap(
            dpi=config.pdf_render_dpi,
            colorspace=pymupdf.csRGB,
            alpha=False,
        )
        rendered_image = pixmap.tobytes("png")
        processed_image = preprocess_image(
            rendered_image,
            config.max_image_side,
            config.max_image_pixels,
            enable_denoise=config.enable_denoise,
            enable_deskew=config.enable_deskew,
        )
        _report_progress(
            progress_callback,
            "loading_model",
            progress,
            f"{page_number}페이지 OCR 모델을 준비하고 있습니다.",
        )
        ocr_result = ocr_service_factory().extract_text(processed_image)
        warnings = [] if ocr_result.text else [f"{page_number}페이지 OCR 결과가 비어 있습니다."]
        confidences = [ocr_result.confidence] if ocr_result.line_count else []
        lines = _lines_for_page(ocr_result.lines, page_number)
        raw_text = ocr_result.raw_text or ocr_result.text
        return ocr_result.text, raw_text, confidences, warnings, lines
    except OcrUnavailableError:
        raise
    except DocumentProcessingError as exc:
        logger.exception("스캔 PDF 페이지 OCR 실패: page=%d", page_number)
        return "", "", [], [f"{page_number}페이지 OCR 처리에 실패했습니다: {exc}"], []


def _process_hybrid_page(
    page: pymupdf.Page,
    page_number: int,
    config: OcrProcessingConfig,
    ocr_service_factory: Callable[[], OcrEngine],
    progress_callback: ProgressCallback | None,
    progress: int,
) -> tuple[str, str, list[float], list[str], int, list[OcrLine]]:
    """Native Text 블록 사이의 이미지 위치에 OCR 결과를 삽입합니다."""

    merged_parts: list[str] = []
    raw_merged_parts: list[str] = []
    lines: list[OcrLine] = []
    confidences: list[float] = []
    warnings: list[str] = []
    processed_images = 0
    page_area = max(page.rect.width * page.rect.height, 1)
    blocks = page.get_text("dict", sort=True).get("blocks", [])

    for block in blocks:
        block_type = block.get("type")
        if block_type == 0:
            native_block_text = _text_from_block(block)
            if native_block_text:
                merged_parts.append(native_block_text)
                raw_merged_parts.append(native_block_text)
            continue

        if block_type != 1 or not _is_significant_image(
            block,
            page_area,
            config.significant_image_area_ratio,
        ):
            continue

        image_content = block.get("image")
        if not image_content:
            continue
        processed_images += 1

        try:
            processed_image = preprocess_image(
                image_content,
                config.max_image_side,
                config.max_image_pixels,
                enable_denoise=config.enable_denoise,
                enable_deskew=config.enable_deskew,
            )
            _report_progress(
                progress_callback,
                "loading_model",
                progress,
                f"{page_number}페이지의 이미지 {processed_images}번을 OCR하고 있습니다.",
            )
            ocr_result = ocr_service_factory().extract_text(processed_image)
        except OcrUnavailableError:
            raise
        except DocumentProcessingError as exc:
            logger.exception("PDF 이미지 영역 OCR 실패: page=%d", page_number)
            warnings.append(
                f"{page_number}페이지의 이미지 영역 OCR 처리에 실패했습니다: {exc}"
            )
            continue

        raw_ocr_text = ocr_result.raw_text or ocr_result.text
        lines.extend(_lines_for_page(ocr_result.lines, page_number))
        if ocr_result.line_count:
            confidences.append(ocr_result.confidence)
        if raw_ocr_text:
            raw_merged_parts.append(f"[이미지 OCR]\n{raw_ocr_text}")

        if ocr_result.text:
            merged_parts.append(f"[이미지 OCR]\n{ocr_result.text}")
        else:
            warnings.append(
                f"{page_number}페이지의 이미지 영역에서 Confidence 기준을 통과한 텍스트를 찾지 못했습니다."
            )

    return (
        "\n\n".join(merged_parts),
        "\n\n".join(raw_merged_parts),
        confidences,
        warnings,
        processed_images,
        lines,
    )


def _lines_for_page(lines: list[OcrLine], page_number: int) -> list[OcrLine]:
    """Engine의 0 기준 Line을 실제 PDF Page Index로 다시 표시합니다."""

    return [replace(line, page=page_number - 1) for line in lines]


def _significant_image_blocks(
    page: pymupdf.Page,
    minimum_area_ratio: float,
) -> list[dict]:
    page_area = max(page.rect.width * page.rect.height, 1)
    blocks = page.get_text("dict", sort=True).get("blocks", [])
    return [
        block
        for block in blocks
        if block.get("type") == 1
        and _is_significant_image(block, page_area, minimum_area_ratio)
    ]


def _is_significant_image(
    block: dict,
    page_area: float,
    minimum_area_ratio: float,
) -> bool:
    bbox = block.get("bbox", (0, 0, 0, 0))
    if len(bbox) < 4:
        return False
    width = max(float(bbox[2]) - float(bbox[0]), 0)
    height = max(float(bbox[3]) - float(bbox[1]), 0)
    return width * height / page_area >= minimum_area_ratio


def _text_from_block(block: dict) -> str:
    lines: list[str] = []
    for line in block.get("lines", []):
        line_text = "".join(
            str(span.get("text", "")) for span in line.get("spans", [])
        ).strip()
        if line_text:
            lines.append(line_text)
    return "\n".join(lines)


def _classify_document_type(page_sources: list[str]) -> str:
    if page_sources and all(source in {"ocr", "empty"} for source in page_sources):
        return "scanned_pdf"
    if any(source in {"ocr", "hybrid"} for source in page_sources):
        return "hybrid_pdf"
    return "digital_pdf"


def _report_progress(
    callback: ProgressCallback | None,
    stage: str,
    progress: int,
    message: str,
) -> None:
    if callback is not None:
        callback(stage, max(0, min(progress, 99)), message)
