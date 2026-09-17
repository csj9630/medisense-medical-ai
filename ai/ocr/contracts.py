"""Framework와 무관한 OCR 입력, 설정, 중간 결과 계약을 정의합니다."""

from dataclasses import dataclass, field
from typing import Callable, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image

ProgressCallback = Callable[[str, int, str], None]


@dataclass(frozen=True)
class OcrDocumentInput:
    """Backend, Worker, Local Lab이 공통 Core에 전달하는 Bytes 입력입니다."""

    file_name: str
    content_type: str
    content: bytes


@dataclass(frozen=True)
class OcrProcessingConfig:
    """문서 검증, 전처리와 OCR 판단에 사용하는 공통 설정입니다."""

    max_file_bytes: int
    max_pdf_pages: int
    native_text_min_chars: int
    significant_image_area_ratio: float
    pdf_render_dpi: int
    max_image_side: int
    max_image_pixels: int
    paddle_device: str
    paddle_language: str
    max_office_uncompressed_bytes: int = 200 * 1024 * 1024
    max_office_archive_entries: int = 5_000
    min_confidence: float = 0.5
    enable_denoise: bool = True
    enable_deskew: bool = True


@dataclass(frozen=True)
class ValidatedDocument:
    """Binary 검증을 통과해 형식별 추출기에 전달할 문서입니다."""

    file_name: str
    content_type: str
    file_type: str
    content: bytes


@dataclass(frozen=True)
class OcrLine:
    """PaddleOCR가 인식한 실제 한 줄의 Text와 위치 정보입니다."""

    text: str
    confidence: float
    page: int = 0
    box: tuple[float, ...] | None = None
    source: str = "ocr"


@dataclass(frozen=True)
class OcrEngineResult:
    """PaddleOCR의 복잡한 반환값을 추출기가 소비할 형태로 단순화합니다."""

    text: str
    confidence: float
    line_count: int
    processing_time_seconds: float
    lines: list[OcrLine] = field(default_factory=list)
    raw_text: str = ""


class OcrEngine(Protocol):
    """Image, PDF, Office 추출기가 사용하는 OCR 엔진의 최소 계약입니다."""

    def extract_text(self, image: "Image") -> OcrEngineResult: ...


@dataclass(frozen=True)
class ExtractedDocument:
    """형식별 추출이 끝난 뒤 중심 Pipeline으로 복귀하는 공통 결과입니다."""

    text: str
    page_count: int | None
    document_type: str
    ocr_image_count: int
    average_confidence: float
    warnings: list[str] = field(default_factory=list)
    lines: list[OcrLine] = field(default_factory=list)
    raw_text: str | None = None


@dataclass(frozen=True)
class OcrDocumentResult:
    """모든 문서 형식이 최종적으로 반환하는 Framework 독립 결과입니다."""

    raw_text: str
    cleaned_text: str
    lines: list[OcrLine]
    page_count: int | None
    document_type: str
    ocr_image_count: int
    average_confidence: float
    warnings: list[str] = field(default_factory=list)
