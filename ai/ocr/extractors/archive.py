"""ZIP 내부의 지원 문서를 디스크에 풀지 않고 통합 추출합니다."""

from collections.abc import Callable
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile, ZipInfo

from ..contracts import (
    ExtractedDocument,
    OcrDocumentInput,
    OcrDocumentResult,
    OcrProcessingConfig,
    ProgressCallback,
    ValidatedDocument,
)
from ..errors import DocumentValidationError, OcrError

SUPPORTED_ARCHIVE_MEMBER_EXTENSIONS = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".docx",
    ".pptx",
    ".json",
    ".jsonl",
    ".csv",
    ".txt",
}

MEMBER_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".json": "application/json",
    ".jsonl": "application/x-ndjson",
    ".csv": "text/csv",
    ".txt": "text/plain",
}

ArchiveMemberAnalyzer = Callable[
    [OcrDocumentInput, ProgressCallback | None],
    OcrDocumentResult,
]


def process_zip_document(
    document: ValidatedDocument,
    config: OcrProcessingConfig,
    analyze_member: ArchiveMemberAnalyzer,
    progress_callback: ProgressCallback | None = None,
) -> ExtractedDocument:
    """ZIP Entry를 각각 기존 Pipeline으로 처리한 뒤 파일명 구분자와 합칩니다."""

    text_sections: list[str] = []
    raw_sections: list[str] = []
    warnings: list[str] = []
    lines = []
    confidence_total = 0.0
    confidence_weight = 0
    ocr_image_count = 0
    successful_members = 0

    try:
        with ZipFile(BytesIO(document.content)) as archive:
            members = [
                entry
                for entry in archive.infolist()
                if not entry.is_dir()
                and Path(entry.filename).suffix.lower()
                in SUPPORTED_ARCHIVE_MEMBER_EXTENSIONS
            ]
            unsupported_count = sum(
                not entry.is_dir()
                and Path(entry.filename).suffix.lower()
                not in SUPPORTED_ARCHIVE_MEMBER_EXTENSIONS
                for entry in archive.infolist()
            )

            for index, entry in enumerate(members):
                display_name = _safe_display_name(entry)
                if entry.file_size > config.max_file_bytes:
                    warnings.append(
                        f"ZIP 내부 {display_name} 제외: 개별 파일 크기 제한을 초과했습니다."
                    )
                    continue

                nested_progress = _member_progress_callback(
                    progress_callback,
                    index,
                    len(members),
                    display_name,
                )
                try:
                    content = archive.read(entry)
                    extension = Path(entry.filename).suffix.lower()
                    result = analyze_member(
                        OcrDocumentInput(
                            file_name=display_name,
                            content_type=MEMBER_CONTENT_TYPES[extension],
                            content=content,
                        ),
                        nested_progress,
                    )
                except OcrError as exc:
                    warnings.append(f"ZIP 내부 {display_name} 제외: {exc}")
                    continue

                heading = f"## ZIP 내부 파일: {display_name}"
                text_sections.append(f"{heading}\n\n{result.cleaned_text}")
                raw_sections.append(f"{heading}\n\n{result.raw_text}")
                lines.extend(
                    replace(line, source=f"{display_name}:{line.source}")
                    for line in result.lines
                )
                warnings.extend(f"{display_name}: {warning}" for warning in result.warnings)
                weight = max(len(result.cleaned_text), 1)
                confidence_total += result.average_confidence * weight
                confidence_weight += weight
                ocr_image_count += result.ocr_image_count
                successful_members += 1

            if unsupported_count:
                warnings.append(
                    f"ZIP에서 지원하지 않는 내부 파일 {unsupported_count}개를 건너뛰었습니다."
                )
    except (BadZipFile, NotImplementedError, RuntimeError, OSError, ValueError) as exc:
        raise DocumentValidationError("손상되었거나 읽을 수 없는 ZIP 파일입니다.") from exc

    if successful_members == 0:
        raise DocumentValidationError("ZIP 내부에서 분석할 수 있는 문서를 찾지 못했습니다.")
    warnings.insert(0, f"ZIP 내부 문서 {successful_members}개를 통합했습니다.")

    return ExtractedDocument(
        text="\n\n".join(text_sections),
        raw_text="\n\n".join(raw_sections),
        page_count=None,
        document_type="zip_archive",
        ocr_image_count=ocr_image_count,
        average_confidence=(
            confidence_total / confidence_weight if confidence_weight else 0.0
        ),
        warnings=warnings,
        lines=lines,
    )


def _safe_display_name(entry: ZipInfo) -> str:
    return entry.filename.replace("\\", "/").replace("\r", " ").replace("\n", " ")


def _member_progress_callback(
    callback: ProgressCallback | None,
    index: int,
    total: int,
    display_name: str,
) -> ProgressCallback | None:
    if callback is None:
        return None

    def report(stage: str, progress: int, message: str) -> None:
        mapped_progress = 25 + int(((index + progress / 100) / max(total, 1)) * 53)
        callback(
            stage,
            min(mapped_progress, 79),
            f"ZIP 내부 {index + 1}/{total} ({display_name}): {message}",
        )

    return report
