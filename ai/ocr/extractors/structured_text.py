"""JSON/JSONL/CSV/TXT를 RAG에 사용할 Text로 직접 추출합니다."""

import csv
import json
from io import StringIO

from ..contracts import ExtractedDocument, ValidatedDocument
from ..errors import DocumentValidationError


def process_structured_text_document(document: ValidatedDocument) -> ExtractedDocument:
    extension = f".{document.file_type}"
    text = extract_structured_text(document.content, extension)
    return ExtractedDocument(
        text=text,
        raw_text=text,
        page_count=None,
        document_type=f"{document.file_type}_direct",
        ocr_image_count=0,
        average_confidence=1.0 if text.strip() else 0.0,
    )


def extract_structured_text(content: bytes, extension: str) -> str:
    """일반 Text는 원문을 보존하고 JSON 계열은 문법을 검증한 뒤 읽기 좋게 정리합니다."""

    text = _decode_text(content, extension)
    if extension == ".json":
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise DocumentValidationError(
                f"JSON 문법이 올바르지 않습니다: {exc.msg} (line {exc.lineno})"
            ) from exc
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except (RecursionError, ValueError) as exc:
            raise DocumentValidationError("JSON 구조가 너무 깊거나 올바르지 않습니다.") from exc

    if extension == ".jsonl":
        records: list[str] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DocumentValidationError(
                    f"JSONL {line_number}번 줄의 JSON 문법이 올바르지 않습니다."
                ) from exc
            try:
                records.append(json.dumps(value, ensure_ascii=False))
            except (RecursionError, ValueError) as exc:
                raise DocumentValidationError(
                    f"JSONL {line_number}번 줄의 JSON 구조가 너무 깊거나 올바르지 않습니다."
                ) from exc
        return "\n".join(records)

    if extension == ".csv":
        try:
            # strict Reader로 따옴표 등이 손상된 CSV를 검증하되 원문은 그대로 유지합니다.
            for _row in csv.reader(StringIO(text), strict=True):
                pass
        except csv.Error as exc:
            raise DocumentValidationError("손상되었거나 읽을 수 없는 CSV 파일입니다.") from exc
    return text


def _decode_text(content: bytes, extension: str) -> str:
    encodings = ["utf-8-sig"]
    if content.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings.insert(0, "utf-16")
    encodings.append("cp949")

    for encoding in encodings:
        try:
            text = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        if "\x00" in text:
            break
        return text

    label = extension.removeprefix(".").upper()
    raise DocumentValidationError(
        f"{label} 파일의 문자 인코딩을 읽을 수 없습니다. "
        "UTF-8, UTF-16 또는 CP949로 저장해 주세요."
    )
