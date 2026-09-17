"""RAG ingestion 전 품질 필터. 여기 있는 규칙은 전부 "통째로 거부"만 한다 - 문자
단위로 지우거나 고쳐 쓰지 않는다. 의료 텍스트에서 숫자/단위/%/약물명/영문 약어/
질환 코드/날짜/괄호는 의미 그 자체라서, 특수문자를 일괄 삭제하는 식의 cleaning은
절대 하지 않는다(팀 스펙의 명시적 요구사항).
"""
import re

MIN_CONTENT_CHARS = 15

# 교체 문자(디코딩 실패 표식, U+FFFD)와 제어문자 - 사용자에게 보일 이유가 전혀 없는
# 깨진 데이터의 신호. 정상적인 한국어 의료 텍스트에는 나타나지 않는다.
_BROKEN_UNICODE = re.compile("[�\x00-\x08\x0b\x0c\x0e-\x1f]")

# 스크래핑/템플릿 잔재 - 남은 HTML 태그, HTML entity, Jinja류 템플릿 placeholder.
_HTML_GARBAGE = re.compile(r"<[a-zA-Z/][^>]{0,80}>|&[a-z]+;|\{\{.*?\}\}")

# instruction-tuning 포맷이 그대로 새어 들어온 흔적 - 채팅 템플릿 스캐폴딩이 남은 행.
_PROMPT_WRAPPER = re.compile(
    r"(?im)^\s*(system\s*:|###\s*instruction|<\|.*?\|>|assistant\s*:|user\s*:)"
)

# 한글/영문/숫자/공백/기본 문장부호가 아닌 문자의 비율이 너무 높으면 인코딩이 깨졌거나
# 번역이 뭉개진 것으로 본다. 임계값은 보수적으로(30%) 잡아서 정상적인 의학 기호
# 조합(예: "AST/ALT", 그리스 문자)까지 걸러지지 않게 한다.
_ALLOWED_CHARS = re.compile("[가-힣a-zA-Z0-9\\s.,%()\\-/·α-ω]")
_JUNK_RATIO_THRESHOLD = 0.3


def is_empty_or_too_short(text: str, min_chars: int = MIN_CONTENT_CHARS) -> bool:
    return len(text.strip()) < min_chars


def has_broken_unicode(text: str) -> bool:
    return bool(_BROKEN_UNICODE.search(text))


def has_html_garbage(text: str) -> bool:
    return bool(_HTML_GARBAGE.search(text))


def is_prompt_template_wrapper(text: str) -> bool:
    return bool(_PROMPT_WRAPPER.search(text))


def is_context_broken(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    junk = len(_ALLOWED_CHARS.sub("", stripped))
    return (junk / len(stripped)) > _JUNK_RATIO_THRESHOLD


def clean_content(text: str) -> str | None:
    """공백만 정리(strip)하고, 위 규칙 중 하나라도 걸리면 None(전체 거부)을 반환한다.
    문자를 지우거나 바꾸는 규칙은 없다 - 통과 아니면 탈락, 둘 중 하나뿐이다."""
    stripped = text.strip()
    if is_empty_or_too_short(stripped):
        return None
    if has_broken_unicode(stripped):
        return None
    if has_html_garbage(stripped):
        return None
    if is_prompt_template_wrapper(stripped):
        return None
    if is_context_broken(stripped):
        return None
    return stripped
