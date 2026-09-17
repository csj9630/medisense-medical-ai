"""Bytes 기반 OCR 입력의 파일명, MIME, Binary 구조와 제한을 검증합니다."""

from io import BytesIO
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

import pymupdf
from PIL import Image, UnidentifiedImageError

from .contracts import OcrDocumentInput, OcrProcessingConfig, ValidatedDocument
from .errors import DocumentTooLargeError, DocumentValidationError
from .extractors.archive import SUPPORTED_ARCHIVE_MEMBER_EXTENSIONS
from .extractors.structured_text import extract_structured_text

SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
SUPPORTED_OFFICE_EXTENSIONS = {".docx", ".pptx"}
SUPPORTED_TEXT_EXTENSIONS = {".json", ".jsonl", ".csv", ".txt"}
SUPPORTED_ARCHIVE_EXTENSIONS = {".zip"}
SUPPORTED_PDF_MIME_TYPES = {"application/pdf", "application/octet-stream"}
SUPPORTED_IMAGE_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "application/octet-stream",
}
SUPPORTED_OFFICE_MIME_TYPES = {
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
        "application/zip",
        "application/x-zip-compressed",
    },
    ".pptx": {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/octet-stream",
        "application/zip",
        "application/x-zip-compressed",
    },
}
SUPPORTED_TEXT_MIME_TYPES = {
    ".json": {
        "application/json",
        "text/json",
        "text/plain",
        "application/octet-stream",
    },
    ".jsonl": {
        "application/json",
        "application/jsonl",
        "application/ndjson",
        "application/x-ndjson",
        "text/plain",
        "application/octet-stream",
    },
    ".csv": {
        "text/csv",
        "text/comma-separated-values",
        "application/csv",
        "application/vnd.ms-excel",
        "text/plain",
        "application/octet-stream",
    },
    ".txt": {"text/plain", "application/octet-stream"},
}
SUPPORTED_ARCHIVE_MIME_TYPES = {
    "application/zip",
    "application/x-zip-compressed",
    "application/octet-stream",
}
OFFICE_REQUIRED_PARTS = {
    ".docx": {"[Content_Types].xml", "_rels/.rels", "word/document.xml"},
    ".pptx": {"[Content_Types].xml", "_rels/.rels", "ppt/presentation.xml"},
}


def validate_document(
    document: OcrDocumentInput,
    config: OcrProcessingConfig,
) -> ValidatedDocument:
    """파일명 → 크기 → MIME → 실제 Binary 구조 순서로 검증합니다."""

    raw_file_name = document.file_name.replace("\\", "/")
    file_name = Path(raw_file_name).name
    extension = Path(file_name).suffix.lower()
    content_type = (
        (document.content_type or "application/octet-stream")
        .split(";", 1)[0]
        .strip()
        .lower()
    )
    supported_extensions = (
        SUPPORTED_IMAGE_EXTENSIONS
        | SUPPORTED_OFFICE_EXTENSIONS
        | SUPPORTED_TEXT_EXTENSIONS
        | SUPPORTED_ARCHIVE_EXTENSIONS
        | {".pdf"}
    )

    if not file_name or extension not in supported_extensions:
        raise DocumentValidationError(
            "PDF, PNG, JPG, DOCX, PPTX, JSON, JSONL, CSV, TXT, ZIP 파일만 "
            "업로드할 수 있습니다."
        )
    if not document.content:
        raise DocumentValidationError("빈 파일은 분석할 수 없습니다.")
    if len(document.content) > config.max_file_bytes:
        max_size_mb = config.max_file_bytes // (1024 * 1024)
        raise DocumentTooLargeError(
            f"파일 크기는 {max_size_mb}MB 이하여야 합니다."
        )

    if extension == ".pdf":
        validate_pdf_content(document.content, content_type, config.max_pdf_pages)
        file_type = "pdf"
    elif extension in SUPPORTED_OFFICE_EXTENSIONS:
        _validate_office_document(document.content, extension, content_type, config)
        file_type = extension.removeprefix(".")
    elif extension in SUPPORTED_TEXT_EXTENSIONS:
        _validate_text_document(document.content, extension, content_type)
        file_type = extension.removeprefix(".")
    elif extension in SUPPORTED_ARCHIVE_EXTENSIONS:
        _validate_zip_document(document.content, content_type, config)
        file_type = "zip"
    else:
        _validate_image(
            document.content,
            extension,
            content_type,
            config.max_image_pixels,
        )
        file_type = "image"

    return ValidatedDocument(
        file_name=file_name,
        content_type=content_type,
        file_type=file_type,
        content=document.content,
    )


def _validate_text_document(
    content: bytes,
    extension: str,
    content_type: str,
) -> None:
    """Text 기반 파일의 MIME과 Encoding/형식을 검증합니다."""

    if content_type not in SUPPORTED_TEXT_MIME_TYPES[extension]:
        raise DocumentValidationError(
            f"{extension.removeprefix('.').upper()} 파일의 MIME Type이 올바르지 않습니다."
        )

    # 파싱을 통해 Binary 위장과 손상된 JSON/CSV를 저장 전에 거부합니다.
    extract_structured_text(content, extension)


def _validate_zip_document(
    content: bytes,
    content_type: str,
    config: OcrProcessingConfig,
) -> None:
    """ZIP을 파일시스템에 풀지 않고 경로·암호화·크기·CRC를 검증합니다."""

    if content_type not in SUPPORTED_ARCHIVE_MIME_TYPES:
        raise DocumentValidationError("ZIP 파일의 MIME Type이 올바르지 않습니다.")

    try:
        with ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > config.max_office_archive_entries:
                raise DocumentValidationError(
                    "ZIP 내부 파일 수가 허용 범위를 초과했습니다."
                )

            total_uncompressed_bytes = 0
            supported_member_count = 0
            for entry in entries:
                normalized_name = entry.filename.replace("\\", "/")
                path = PurePosixPath(normalized_name)
                if path.is_absolute() or ".." in path.parts:
                    raise DocumentValidationError(
                        "ZIP에 안전하지 않은 내부 경로가 포함되어 있습니다."
                    )
                if entry.flag_bits & 0x1:
                    raise DocumentValidationError("암호화된 ZIP 파일은 분석할 수 없습니다.")

                total_uncompressed_bytes += entry.file_size
                if total_uncompressed_bytes > config.max_office_uncompressed_bytes:
                    raise DocumentValidationError(
                        "ZIP의 압축 해제 크기가 허용 범위를 초과했습니다."
                    )
                if (
                    not entry.is_dir()
                    and Path(normalized_name).suffix.lower()
                    in SUPPORTED_ARCHIVE_MEMBER_EXTENSIONS
                ):
                    supported_member_count += 1

            if supported_member_count == 0:
                raise DocumentValidationError(
                    "ZIP 내부에 지원하는 문서 파일이 없습니다."
                )
            if archive.testzip() is not None:
                raise DocumentValidationError("손상되었거나 읽을 수 없는 ZIP 파일입니다.")
    except DocumentValidationError:
        raise
    except (BadZipFile, NotImplementedError, RuntimeError, OSError, ValueError) as exc:
        raise DocumentValidationError("손상되었거나 읽을 수 없는 ZIP 파일입니다.") from exc


def validate_pdf_content(content: bytes, content_type: str, max_pages: int) -> None:
    """PDF Signature, 암호화, 페이지 수와 각 Page 객체를 확인합니다."""

    if content_type not in SUPPORTED_PDF_MIME_TYPES:
        raise DocumentValidationError("PDF 파일의 MIME Type이 올바르지 않습니다.")
    if b"%PDF-" not in content[:1024]:
        raise DocumentValidationError("PDF signature를 확인할 수 없습니다.")

    try:
        with pymupdf.open(stream=content, filetype="pdf") as pdf:
            if pdf.needs_pass or pdf.is_encrypted:
                raise DocumentValidationError("암호화된 PDF는 분석할 수 없습니다.")
            if pdf.page_count == 0:
                raise DocumentValidationError("페이지가 없는 PDF는 분석할 수 없습니다.")
            if pdf.page_count > max_pages:
                raise DocumentValidationError(
                    f"PDF는 최대 {max_pages}페이지까지 분석할 수 있습니다."
                )
            for page_number in range(pdf.page_count):
                pdf.load_page(page_number)
    except DocumentValidationError:
        raise
    except (pymupdf.FileDataError, RuntimeError, ValueError) as exc:
        raise DocumentValidationError("손상되었거나 읽을 수 없는 PDF입니다.") from exc


def _validate_office_document(
    content: bytes,
    extension: str,
    content_type: str,
    config: OcrProcessingConfig,
) -> None:
    """OOXML ZIP 경로, 암호화, Entry 수와 압축 해제 크기를 확인합니다."""

    if content_type not in SUPPORTED_OFFICE_MIME_TYPES[extension]:
        raise DocumentValidationError(
            f"{extension.removeprefix('.').upper()} 파일의 MIME Type이 올바르지 않습니다."
        )

    try:
        with ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > config.max_office_archive_entries:
                raise DocumentValidationError(
                    "Office 문서의 내부 파일 수가 허용 범위를 초과했습니다."
                )

            total_uncompressed_bytes = 0
            normalized_names: set[str] = set()
            for entry in entries:
                normalized_name = entry.filename.replace("\\", "/")
                path = PurePosixPath(normalized_name)
                if path.is_absolute() or ".." in path.parts:
                    raise DocumentValidationError(
                        "Office 문서에 안전하지 않은 내부 경로가 포함되어 있습니다."
                    )
                if entry.flag_bits & 0x1:
                    raise DocumentValidationError(
                        "암호화된 Office 문서는 분석할 수 없습니다."
                    )

                normalized_names.add(normalized_name)
                total_uncompressed_bytes += entry.file_size
                if total_uncompressed_bytes > config.max_office_uncompressed_bytes:
                    raise DocumentValidationError(
                        "Office 문서의 압축 해제 크기가 허용 범위를 초과했습니다."
                    )

            if not OFFICE_REQUIRED_PARTS[extension].issubset(normalized_names):
                raise DocumentValidationError(
                    "확장자와 실제 Office 문서 형식이 일치하지 않습니다."
                )
            if archive.testzip() is not None:
                raise DocumentValidationError(
                    "손상되었거나 읽을 수 없는 Office 문서입니다."
                )
    except DocumentValidationError:
        raise
    except (BadZipFile, RuntimeError, OSError, ValueError) as exc:
        raise DocumentValidationError(
            "손상되었거나 읽을 수 없는 Office 문서입니다."
        ) from exc


def _validate_image(
    content: bytes,
    extension: str,
    content_type: str,
    max_pixels: int,
) -> None:
    if content_type not in SUPPORTED_IMAGE_MIME_TYPES:
        raise DocumentValidationError("이미지 파일의 MIME Type이 올바르지 않습니다.")

    expected_formats = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG"}
    try:
        with Image.open(BytesIO(content)) as image:
            if image.width * image.height > max_pixels:
                raise DocumentValidationError(
                    "이미지 해상도가 허용 범위를 초과했습니다."
                )
            image.load()
            if image.format != expected_formats[extension]:
                raise DocumentValidationError(
                    "확장자와 실제 이미지 형식이 일치하지 않습니다."
                )
    except DocumentValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise DocumentValidationError("손상되었거나 읽을 수 없는 이미지입니다.") from exc
