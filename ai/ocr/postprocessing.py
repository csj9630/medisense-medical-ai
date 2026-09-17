"""OCR Line과 문서 Text를 손실 없이 정리하는 공통 후처리입니다."""

import re
import unicodedata

from .contracts import OcrLine

CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
EXCESSIVE_BLANK_LINES = re.compile(r"\n{3,}")
TRAILING_SPACES = re.compile(r"[ \t]+\n")


def clean_document_text(text: str) -> str:
    """원문 의미를 바꾸지 않고 제어문자와 과도한 공백만 제거합니다."""

    normalized = unicodedata.normalize("NFKC", text.replace("\r\n", "\n"))
    without_controls = CONTROL_CHARACTERS.sub("", normalized)
    without_trailing_spaces = TRAILING_SPACES.sub("\n", without_controls)
    return EXCESSIVE_BLANK_LINES.sub("\n\n", without_trailing_spaces).strip()


def clean_text(text: str) -> str:
    """기존 공개 동작을 위해 한 줄 안의 중복 공백까지 정리합니다."""

    text = re.sub(r"[ \t]+", " ", text)
    return clean_document_text(text)


def dedupe_consecutive_lines(lines: list[OcrLine]) -> list[OcrLine]:
    """겹치는 감지 Box 때문에 연속으로 반복된 같은 OCR Line만 제거합니다."""

    result: list[OcrLine] = []
    for line in lines:
        if not result or result[-1].text != line.text or result[-1].page != line.page:
            result.append(line)
    return result


def postprocess(lines: list[OcrLine], min_confidence: float = 0.5) -> str:
    """Confidence 기준을 통과한 Line을 Page 순서대로 정제해 합칩니다."""

    kept = dedupe_consecutive_lines(
        [line for line in lines if line.confidence >= min_confidence]
    )
    if not kept:
        return ""

    pages = sorted({line.page for line in kept})
    if len(pages) <= 1:
        return clean_text("\n".join(line.text for line in kept))

    page_texts: list[str] = []
    for page in pages:
        page_text = clean_text(
            "\n".join(line.text for line in kept if line.page == page)
        )
        page_texts.append(f"--- 페이지 {page + 1} ---\n{page_text}")
    return "\n\n".join(page_texts)
