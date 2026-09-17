"""네트워크와 분리된 웹 HTML 텍스트 추출 및 내부 이미지 OCR입니다."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from urllib.parse import urljoin, urlparse

from lxml import etree, html

from ..contracts import OcrDocumentResult, OcrEngine, OcrLine, OcrProcessingConfig
from ..postprocessing import clean_document_text
from ..preprocessing import preprocess_image

CONTENT_MARKER_HINTS = (
    "content",
    "contents",
    "article",
    "detail",
    "document",
    "entry",
    "post",
    "print",
    "view",
)
CONTENT_MARKER_BONUSES = {
    "data-content": 5_000,
    "print-content": 4_500,
    "article-content": 4_000,
    "article-body": 4_000,
    "post-content": 4_000,
    "entry-content": 4_000,
}
NAVIGATION_MARKER_HINTS = (
    "breadcrumb",
    "category",
    "filter",
    "footer",
    "gnb",
    "header",
    "menu",
    "modal",
    "navbar",
    "pagination",
    "popup",
    "search",
    "sidebar",
    "subject-wrap",
)
DECORATIVE_IMAGE_HINTS = (
    "badge",
    "copyright",
    "footer",
    "icon",
    "license",
    "logo",
    "open-box",
)
CONTENT_BLOCK_XPATH = (
    ".//h1|.//h2|.//h3|.//h4|.//h5|.//h6|.//p|.//li|"
    ".//blockquote|.//pre|.//table"
)


@dataclass(frozen=True)
class WebImageCandidate:
    url: str
    label: str


@dataclass(frozen=True)
class ParsedWebDocument:
    title: str
    text: str
    images: list[WebImageCandidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FetchedWebImage:
    url: str
    label: str
    content: bytes


def parse_web_document(html_text: str, base_url: str) -> ParsedWebDocument:
    """HTML에서 RAG에 유효한 본문과 이미지 후보를 DOM 순서로 추출합니다."""

    parser = html.HTMLParser(encoding="utf-8", recover=True)
    try:
        root = html.document_fromstring(html_text, parser=parser, base_url=base_url)
    except (etree.ParserError, ValueError) as exc:
        raise ValueError("웹페이지 HTML 구조를 분석하지 못했습니다.") from exc

    for node in root.xpath(
        "//script|//style|//noscript|//template|//nav|//footer|//iframe|//canvas|//svg"
    ):
        node.drop_tree()
    # 상세 본문 전체를 form으로 감싸는 공공기관 사이트가 있으므로 자식은 보존합니다.
    for node in root.xpath("//form"):
        node.drop_tag()

    title = clean_document_text(" ".join(root.xpath("//title/text()")))
    if not title:
        title = urlparse(base_url).hostname or "웹페이지"

    content_root = _select_content_root(root)
    blocks: list[str] = []
    for node in content_root.xpath(CONTENT_BLOCK_XPATH):
        if any(
            parent.tag in {"p", "li", "blockquote", "pre", "table"}
            for parent in node.iterancestors()
            if parent is not content_root
        ):
            continue
        text_value = clean_document_text(" ".join(node.itertext()))
        if not text_value:
            continue
        if isinstance(node.tag, str) and node.tag.startswith("h") and node.tag[1:].isdigit():
            level = min(max(int(node.tag[1:]), 1), 6)
            text_value = f"{'#' * level} {text_value}"
        blocks.append(text_value)

    if not blocks:
        fallback = clean_document_text(" ".join(content_root.itertext()))
        if fallback:
            blocks.append(fallback)

    images: list[WebImageCandidate] = []
    seen_urls: set[str] = set()
    for image_node in content_root.xpath(".//img"):
        raw_url = _image_source(image_node)
        if not raw_url or raw_url.startswith(("data:", "blob:")):
            continue
        absolute_url = urljoin(base_url, raw_url)
        if _is_decorative_image(image_node, absolute_url):
            continue
        if absolute_url in seen_urls:
            continue
        seen_urls.add(absolute_url)
        label = clean_document_text(
            image_node.get("alt", "")
            or image_node.get("title", "")
            or f"웹페이지 이미지 {len(images) + 1}"
        )
        images.append(WebImageCandidate(url=absolute_url, label=label))

    return ParsedWebDocument(
        title=title[:255],
        text=clean_document_text("\n\n".join(blocks)),
        images=images,
    )


def build_web_ocr_result(
    parsed: ParsedWebDocument,
    images: list[FetchedWebImage],
    config: OcrProcessingConfig,
    engine: OcrEngine,
    *,
    image_warnings: list[str] | None = None,
) -> OcrDocumentResult:
    """직접 추출 본문 뒤에 유효한 내부 이미지의 PaddleOCR 결과를 합칩니다."""

    sections = [parsed.text] if parsed.text else []
    lines: list[OcrLine] = []
    confidences: list[float] = []
    warnings = [*parsed.warnings, *(image_warnings or [])]
    ocr_image_count = 0

    for index, image in enumerate(images, start=1):
        try:
            processed = preprocess_image(
                image.content,
                max_image_side=config.max_image_side,
                max_image_pixels=config.max_image_pixels,
                enable_denoise=config.enable_denoise,
                enable_deskew=config.enable_deskew,
            )
            result = engine.extract_text(processed)
        except Exception as exc:
            warnings.append(f"내부 이미지 {index} OCR을 건너뛰었습니다: {type(exc).__name__}")
            continue
        if not result.text.strip():
            warnings.append(f"내부 이미지 {index}에서 인식 가능한 텍스트를 찾지 못했습니다.")
            continue
        ocr_image_count += 1
        confidences.append(result.confidence)
        lines.extend(
            replace(line, page=index - 1, source="web_image_ocr")
            for line in result.lines
        )
        sections.append(f"## 웹페이지 이미지 OCR: {image.label}\n\n{result.text}")

    cleaned = clean_document_text("\n\n".join(sections))
    return OcrDocumentResult(
        raw_text=cleaned,
        cleaned_text=cleaned,
        lines=lines,
        page_count=None,
        document_type="web_page",
        ocr_image_count=ocr_image_count,
        average_confidence=(
            sum(confidences) / len(confidences) if confidences else 1.0
        ),
        warnings=warnings,
    )


def _image_source(node: etree._Element) -> str:
    for attribute in ("src", "data-src", "data-original", "data-lazy-src"):
        value = node.get(attribute, "").strip()
        if value:
            return value
    srcset = node.get("srcset", "").strip()
    if srcset:
        return srcset.split(",")[0].strip().split(" ")[0]
    return ""


def _select_content_root(root: etree._Element) -> etree._Element:
    """첫 semantic tag가 아니라 실제 본문 밀도가 가장 높은 컨테이너를 고릅니다."""

    candidates: list[etree._Element] = list(
        root.xpath("//main|//*[@role='main']|//article")
    )
    for node in root.iter():
        if node.tag not in {"div", "section"}:
            continue
        marker = _element_marker(node)
        if any(hint in marker for hint in CONTENT_MARKER_HINTS):
            candidates.append(node)

    if not candidates:
        body_nodes = root.xpath("//body")
        return body_nodes[0] if body_nodes else root

    unique_candidates = list(dict.fromkeys(candidates))
    return max(unique_candidates, key=_content_candidate_score)


def _content_candidate_score(node: etree._Element) -> float:
    marker = _element_marker(node)
    block_text = clean_document_text(
        "\n".join(
            " ".join(block.itertext())
            for block in node.xpath(CONTENT_BLOCK_XPATH)
        )
    )
    all_text = clean_document_text(" ".join(node.itertext()))
    link_text_length = sum(
        len(clean_document_text(" ".join(link.itertext())))
        for link in node.xpath(".//a")
    )
    control_count = len(node.xpath(".//button|.//input|.//select|.//textarea"))

    score = len(block_text) + min(len(all_text), 30_000) * 0.08
    if node.tag == "main" or node.get("role", "").lower() == "main":
        score += 2_000
    elif node.tag == "article":
        score += 1_000
    score += sum(
        bonus for hint, bonus in CONTENT_MARKER_BONUSES.items() if hint in marker
    )
    if any(hint in marker for hint in NAVIGATION_MARKER_HINTS):
        score -= 6_000
    score -= link_text_length * 0.7
    score -= control_count * 80
    return score


def _element_marker(node: etree._Element) -> str:
    return f"{node.get('id', '')} {node.get('class', '')}".lower().replace("_", "-")


def _is_decorative_image(node: etree._Element, absolute_url: str) -> bool:
    markers = [_element_marker(node)]
    markers.extend(
        _element_marker(parent)
        for parent in list(node.iterancestors())[:5]
    )
    url_marker = absolute_url.lower().replace("_", "-")
    return any(
        hint in marker
        for hint in DECORATIVE_IMAGE_HINTS
        for marker in [*markers, url_marker]
    )
