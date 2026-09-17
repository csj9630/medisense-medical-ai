"""LLM 응답이 나간 뒤, 시스템 프롬프트가 놓쳤을 수도 있는 위험한 표현을 잡아내는
마지막 안전망. 프롬프트로만 막고 있던 것에 대한 이중 안전장치.

지금은 구체적인 약물 용량/처방 패턴만 정규식으로 잡는다 — 확정적 진단 표현("~입니다")
자체를 자동으로 순화하는 건 정교한 NLP나 LLM 재작성이 필요해서 범위 밖으로 뒀다
(TODO, ai/consultation/CLAUDE.md 참고).
"""
import json
import re
from functools import lru_cache

_RISKY_DOSAGE_PATTERNS = (
    re.compile(r"\d+\s?mg"),
    re.compile(r"\d+\s?ml", re.IGNORECASE),
    # "3정" 같은 처방 단위. "2정도"/"3정확히"처럼 흔히 뒤따라오는 단어만 골라 제외한다
    # (뒤에 한글이 오면 무조건 제외하면 "3정씩"/"3정을" 같은 정상 케이스까지 놓친다).
    re.compile(r"\d+\s?정(?!도|확|말|보|신|리|지|상)"),
)

_DOSAGE_WARNING = "\n\n[안전 안내] 구체적인 약물 용량/처방은 반드시 의사·약사와 상담 후 결정하세요."

# 토크나이저 종료/시작 특수 토큰이 디코딩 과정에서 그대로 텍스트에 섞여 나오는 경우가
# 있었다("...</s></s>") — 사용자에게 보일 이유가 전혀 없는 내부 토큰이라 몇 번 나오든
# 무조건 제거한다(반복 횟수 조건 없음).
_SPECIAL_TOKEN_PATTERN = re.compile(r"</?s>")

# 시스템 프롬프트가 마크다운 문법(굵게/기울임/목록/제목)을 쓰지 말라고 지시해도, 소형
# 모델이 학습 데이터 습관대로 "**굵게**"나 "*   목록" 형태를 절반 가까이 계속 섞어
# 낸다(프롬프트를 두 번 강화해도 완전히는 안 없어짐 — 실제 A/B 테스트로 확인). 프롬프트
# 지시만으로는 못 믿으므로, 응급 키워드 하드 필터와 같은 원칙으로 여기서도 결정적으로
# 제거하는 이중 안전장치를 둔다. 굵게/기울임은 기호만 벗기고 안의 텍스트는 살리고,
# 줄 맨 앞 목록 기호(-, *, •)와 제목 기호(#)는 그 줄의 안내문처럼 자연스럽게 남도록
# 기호만 지운다(줄 자체를 하나의 문장으로 합치지는 않음 — 내용을 임의로 재작성하지
# 않기 위함).
_BOLD_PATTERN = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_PATTERN = re.compile(r"(?<!\*)\*([^\*\n]+?)\*(?!\*)")
_INLINE_CODE_PATTERN = re.compile(r"`([^`\n]+?)`")
_CODE_FENCE_LINE_PATTERN = re.compile(r"(?m)^\s*```\w*\s*$")
_LEADING_LIST_MARKER_PATTERN = re.compile(r"(?m)^[ \t]*[*\-•][ \t]+")
_LEADING_HEADING_MARKER_PATTERN = re.compile(r"(?m)^[ \t]*#{1,6}[ \t]*")


def _strip_markdown_syntax(text: str) -> str:
    text = _CODE_FENCE_LINE_PATTERN.sub("", text)
    text = _INLINE_CODE_PATTERN.sub(r"\1", text)
    text = _BOLD_PATTERN.sub(r"\1", text)
    text = _ITALIC_PATTERN.sub(r"\1", text)
    text = _LEADING_LIST_MARKER_PATTERN.sub("", text)
    text = _LEADING_HEADING_MARKER_PATTERN.sub("", text)
    return text


# 프롬프트에서 "면책 문구는 백엔드가 자동으로 붙이니 직접 쓰지 말라"고 지시해도, 일부
# 모델이 자기 나름의 면책 문구를 답변 끝에 덧붙이는 경우가 관찰됐다("**면책 조항:**
# 저는 의료 전문가가 아니므로...") — 실제 면책 문구는 프론트엔드 배너가 담당하므로
# 이런 자체 생성 문단은 중복이자 잡음이다. 마지막 문단이 이런 신호를 담고 있으면 제거한다.
_SELF_DISCLAIMER_SIGNALS = (
    "면책 조항",
    "면책조항",
    "disclaimer",
    "의료 전문가가 아니",
    "전문가가 아니므로",
    "전문적인 의학적 조언을 대체",
    "의학적 조언으로 간주",
    "의학적 조언으로 해석",
)


def _strip_special_tokens(text: str) -> str:
    return _SPECIAL_TOKEN_PATTERN.sub("", text)


def _strip_self_generated_disclaimer(text: str) -> str:
    paragraphs = text.split("\n\n")
    if len(paragraphs) < 2:
        return text
    last = paragraphs[-1].strip().lower()
    if last and any(signal in last for signal in _SELF_DISCLAIMER_SIGNALS):
        return "\n\n".join(paragraphs[:-1]).rstrip()
    return text

# 일부 원격 모델이 정상 답변을 다 낸 뒤에도 멈추지 않고 같은 줄이나 몇 줄짜리 패턴
# ("[]" 반복, "caution: .../indicator: ..." 번갈아 반복 등)을 max_tokens까지 채우는
# 경우가 관찰됐다 — 매번 반복되는 내용이 달라서 특정 문자열 하나만 정규식으로 잡을 수
# 없다. 대신 "1~4줄짜리 어떤 패턴이 끝에서부터 연속으로 여러 번 반복되는지"만 일반적으로
# 검사한다 — 프롬프트 내용과 무관한 모델/서버 쪽 종료 토큰 처리 문제로 보이며, 반복이
# 시작되기 전까지의 정상 답변은 그대로 둔다.
_MIN_TRAILING_REPEATS = 3
_MAX_REPEAT_UNIT_LINES = 4


def _strip_trailing_repeated_lines(text: str) -> str:
    lines = text.split("\n")
    non_blank = [(i, line.strip().lower()) for i, line in enumerate(lines) if line.strip()]
    if not non_blank:
        return text

    indices = [i for i, _ in non_blank]
    normalized = [content for _, content in non_blank]
    total = len(normalized)

    best_cut: int | None = None
    for unit in range(1, _MAX_REPEAT_UNIT_LINES + 1):
        if total < unit * _MIN_TRAILING_REPEATS:
            continue
        pattern = normalized[total - unit :]
        repeats = 1
        pos = total - unit
        while pos - unit >= 0 and normalized[pos - unit : pos] == pattern:
            repeats += 1
            pos -= unit
        if repeats >= _MIN_TRAILING_REPEATS:
            cut_line_index = indices[pos]
            if best_cut is None or cut_line_index < best_cut:
                best_cut = cut_line_index

    if best_cut is None:
        return text
    return "\n".join(lines[:best_cut]).rstrip()


# 정상 답변이 다 끝난 뒤, 반복은 아니지만(그래서 위 함수가 못 잡음) 딱 한 번씩만
# JSON 조각이나 "라벨: 0.8"/"모델"/"DisplayName: ..." 같은 메타 텍스트를 덧붙이는
# 경우가 실제로 관찰됐다. 오탐으로 정상 문장을 지우면 안 되므로 아주 명확한 신호만
# 좁게 잡는다 — 전체가 유효한 JSON으로 파싱되는 꼬리 블록, 그리고 알려진 라벨
# 키워드로 시작하는 짧은 한 줄짜리 텍스트만 대상으로 한다.
def _strip_trailing_json_block(text: str) -> str:
    idx = text.rfind("{")
    if idx == -1:
        return text
    candidate = text[idx:].strip()
    if not candidate.endswith("}"):
        return text
    try:
        json.loads(candidate)
    except ValueError:
        return text
    return text[:idx].rstrip()


_TRAILING_LABEL_LINE_PATTERN = re.compile(r"^(?:라벨|모델|Label|Model|DisplayName)\s*[:：]?\s*.{0,60}$")


def _strip_trailing_label_leak(text: str) -> str:
    lines = text.split("\n")
    while lines:
        candidate = lines[-1].strip()
        if not candidate:
            lines.pop()
            continue
        if _TRAILING_LABEL_LINE_PATTERN.match(candidate):
            lines.pop()
            continue
        break
    return "\n".join(lines).rstrip()


# 실제 관찰된 사례 - 정상 답변 뒤에 "라벨```json"으로 시작해서 JSON을 자기요약처럼
# 다시 쓰다가 토큰 한도에 걸려 중간에 끊긴 경우가 있었다("...\"응답\": \"...충"에서
# 끊김). `_strip_trailing_json_block`은 완전한 JSON만 대상으로 하고
# `_strip_trailing_label_leak`은 그 줄이 진짜 마지막 줄일 때만 잡아서, 이렇게 뒤에
# 미완성 JSON 덩어리가 붙어있으면 못 잡는다. "```"가 열렸는데 그 뒤로 안 닫히면
# (즉 마지막으로 등장한 "```") 거기서부터 끝까지는 절대 정상 답변일 수 없으므로
# 그 줄의 시작 지점부터 통째로 잘라낸다.
def _strip_from_unclosed_code_fence(text: str) -> str:
    # "```" 등장 횟수가 짝수면(0번 포함) 전부 쌍을 이뤄 닫혔다는 뜻이라 안 건드린다
    # (정상적으로 닫힌 코드 블록은 _strip_markdown_syntax가 처리). 홀수면 마지막
    # 등장이 못 닫힌 채로 끝났다는 뜻이므로 그 줄의 시작 지점부터 통째로 잘라낸다.
    if text.count("```") % 2 == 0:
        return text
    idx = text.rfind("```")
    line_start = text.rfind("\n", 0, idx) + 1
    return text[:line_start].rstrip()


# 실제 관찰된 사례 - 정상적인 한국어 답변을 다 낸 뒤, 소형 모델이 디코딩 상태가
# 무너지면서("환각 상태") 러시아어 문장을 이어 붙이는 경우가 나왔다
# ("Ещё неясно. Можете помочь мне с этим?..."). 반복도 아니고(그래서
# _strip_trailing_repeated_lines가 못 잡음) JSON/라벨 패턴도 아니라서 별도로 잡는다.
#
# 이제 "사용자가 입력한 언어로 답변" 정책(한/영/일/중 지원)이 생기면서, "허용
# 문자 집합"을 언어 하나로 고정할 수 없다 - 사용자가 영어로 물었는데 한국어
# 문자를 전부 "정상"으로 허용해버리면, 정작 영어 답변 중간에 한국어가 새는
# 진짜 버그를 못 잡는다. 그래서 사용자 질문에서 감지한 입력 언어에 맞는 문자
# 범위만 허용 문자에 추가하고, 그 밖의 문자 비율이 높은 줄만 "다른 언어로 샌
# 꼬리"로 보고 끝에서부터 제거한다. 숫자/기본 문장부호/그리스 문자(α-GT 등
# 의학 기호)/라틴 문자(의학 약어·단위, MRI·CT 등)는 언어와 무관하게 항상 허용한다
# (한국어 질문에 영어 약어가 섞이는 건 정상이라서).
_BASE_ALLOWED_CHARS = r"a-zA-Zα-ωΑ-Ω0-9\s.,!?:;()\-/%·\"'~…∼℃±×÷"
_FOREIGN_LEAK_RATIO_THRESHOLD = 0.3

_HANGUL_PATTERN = re.compile(r"[가-힣]")
_KANA_PATTERN = re.compile(r"[ぁ-んァ-ンー]")
_HAN_PATTERN = re.compile(r"[一-鿿]")

# 언어별로 "정상 답변에 흔히 나오는" 추가 문자 범위. 일본어는 한자를 섞어 쓰므로
# 가나+한자 둘 다 허용한다. 알 수 없는 입력(라틴 문자 위주 등)은 en으로 취급 —
# 다만 아래 detect 함수는 애매하면 프로젝트 기본 언어인 ko로 fallback한다.
_LANGUAGE_EXTRA_CHARS = {
    "ko": "가-힣",
    "ja": "ぁ-んァ-ンー一-鿿",
    "zh": "一-鿿",
    "en": "",
}


def _detect_input_language(text: str) -> str:
    """아주 단순한 문자 범위 기반 판정 - 정교한 언어감지 라이브러리 없이, 이
    프로젝트가 실제로 지원하는 한/영/일/중 정도만 구분하면 충분하다. 문자 종류가
    섞여 있으면 한글 > 가나 > 한자 순으로 우선한다(예: 한국어 문장에 의학
    영단어가 섞여도 한국어로 판정). 어느 쪽도 아니면(빈 문자열, 라틴 문자만 등)
    프로젝트 기본 언어인 한국어로 fallback한다 — 없는 입력을 영어로 잘못
    판정해서 정상적인 한국어 답변을 "외국어 유출"로 오탐 제거하는 사고를
    막기 위함(안전한 쪽으로 fallback)."""
    if _HANGUL_PATTERN.search(text):
        return "ko"
    if _KANA_PATTERN.search(text):
        return "ja"
    if _HAN_PATTERN.search(text):
        return "zh"
    if re.search(r"[a-zA-Z]", text):
        return "en"
    return "ko"


def _allowed_chars_pattern(input_language: str) -> re.Pattern:
    extra = _LANGUAGE_EXTRA_CHARS.get(input_language, "가-힣")
    return re.compile(f"[{_BASE_ALLOWED_CHARS}{extra}]")


# 실제 관찰된 사례 - 프롬프트가 진료과 힌트를 괄호로 감싸서 넘기다 보니(지금은
# 안 그러도록 고쳤지만, 프롬프트 지시만으로는 소형 모델을 100% 못 믿음), 모델이 그
# 스타일을 그대로 따라 해서 "(정형외과에서 진료를 받아보시는 것도 고려해볼 수
# 있습니다.)"처럼 답변 마지막 문장 전체를 괄호로 감싸버렸다. "고열(38도 이상)"처럼
# 정상적인 의학 부연설명 괄호까지 벗기면 안 되므로, 답변 맨 끝이 통째로 괄호로
# 감싸져 있고 그 안에 실제 진료과 이름이 들어있을 때만 괄호를 벗긴다(내용은 보존).
_DEPARTMENT_NAMES = (
    "내과", "순환기내과", "이비인후과", "피부과", "정형외과", "신경과", "안과",
    "산부인과", "비뇨의학과", "정신건강의학과", "소아청소년과",
)
# 괄호뿐 아니라 중괄호로 감싸는 변형도 실제로 관찰됨 - "{정형외과에서 ... 있습니다.}"
_TRAILING_PARENTHETICAL = re.compile(r"[({]([^(){}]*)[)}]\s*$")


def _unwrap_trailing_department_parenthetical(text: str) -> str:
    stripped = text.rstrip()
    match = _TRAILING_PARENTHETICAL.search(stripped)
    if not match:
        return text
    inner = match.group(1).strip()
    if not any(name in inner for name in _DEPARTMENT_NAMES):
        return text
    before = stripped[: match.start()].rstrip()
    return f"{before} {inner}".strip() if before else inner


def _foreign_ratio(text: str, allowed_pattern: re.Pattern) -> float:
    stripped = text.strip()
    if not stripped:
        return 0.0
    allowed = len(allowed_pattern.findall(stripped))
    return 1 - (allowed / len(stripped))


def _strip_trailing_foreign_language_lines(text: str, input_language: str) -> str:
    allowed_pattern = _allowed_chars_pattern(input_language)
    lines = text.split("\n")
    while lines:
        candidate = lines[-1].strip()
        if not candidate:
            lines.pop()
            continue
        if _foreign_ratio(candidate, allowed_pattern) >= _FOREIGN_LEAK_RATIO_THRESHOLD:
            lines.pop()
            continue
        break
    return "\n".join(lines).rstrip()


# 실제 관찰된 사례 - 정상 답변이 끝난 뒤 같은 짧은 조각을 줄바꿈 없이 한 줄 안에서
# 계속 이어붙이는 경우가 있었다("라벨_end{라벨_end{라벨_end{..." 수십 번 반복).
# `_strip_trailing_repeated_lines`는 "줄 전체"가 반복될 때만 잡아서, 이렇게 한 줄
# 안에서 벌어지는 반복은 못 잡는다. 2~30자짜리 조각이 답변 맨 끝까지 3번 이상
# 연달아 반복되면 그 반복이 시작되는 지점부터 잘라낸다.
_INLINE_REPEAT_PATTERN = re.compile(r"(.{2,30}?)\1{2,}\s*$")


def _strip_trailing_inline_repetition(text: str) -> str:
    match = _INLINE_REPEAT_PATTERN.search(text)
    if not match:
        return text
    return text[: match.start()].rstrip()


# 팀원의 RAG 연계 작업지시서(medical_prompt_v4.1)가 지적한 실패 모드 - 소형
# 모델이 정상 답변을 마친 뒤, 사용자와의 새 대화 턴을 스스로 만들어내며
# "환자:"/"의사:"/"user:"/"assistant:" 같은 역할 문자열을 답변에 그대로 출력하는
# 경우가 있다. `_TRAILING_LABEL_LINE_PATTERN`은 "라벨"/"모델" 같은 메타데이터
# 라벨만 잡고 대화 역할 문자열은 못 잡아서 별도로 둔다. 그 줄이 실제로 대화
# 역할 문자열로만 시작할 때만 잡는다(예: "의사소통이 중요합니다"처럼 역할
# 이름을 포함한 정상 문장까지 지우면 안 되므로, 콜론/공백 없이 바로 이어지는
# 문장은 놔둔다 - "의사:"는 잡고 "의사소통"은 안 잡음).
_TRAILING_ROLE_LINE_PATTERN = re.compile(
    r"^(?:user|assistant|system|model|환자|의사|사용자|AI)\s*[:：]\s*.*$", re.IGNORECASE
)


def _strip_trailing_role_strings(text: str) -> str:
    lines = text.split("\n")
    while lines:
        candidate = lines[-1].strip()
        if not candidate:
            lines.pop()
            continue
        if _TRAILING_ROLE_LINE_PATTERN.match(candidate):
            lines.pop()
            continue
        break
    return "\n".join(lines).rstrip()


# 실제 관찰된 사례(2026-09-02, 실 RAG 데이터로 라이브 테스트 중) - 정상 답변을
# 다 낸 뒤, 모델이 자신에게 입력된 system prompt 내용 자체를 답변에 그대로
# 이어붙이는 경우가 있었다("당신은 MediSense의 의료 상담 보조 챗봇입니다...",
# "절대 규칙" 등 system_prompt.md의 실제 문장이 그대로 등장). 이 파일이
# system_prompt.md 내용을 알고 있으니, 그 안에 실제로 있는 문장(15자 이상 -
# 너무 짧으면 우연히 겹칠 위험)이 답변에서 발견되면 그 지점부터 통째로 잘라낸다.
# "DisplayName"/"Example Response"는 system_prompt.md엔 없는 문자열이지만 같은
# 사고에서 실제로 함께 관찰된 마커라 수동으로 추가한다(모델의 파인튜닝 데이터
# 포맷에서 새어나온 것으로 보임 - 우리 프롬프트 내용은 아님).
_MIN_PROMPT_LEAK_MATCH_CHARS = 15
_KNOWN_NON_PROMPT_LEAK_MARKERS = ("DisplayName", "Example Response")

# 위와 같은 부류의 라벨 유출이지만, 이건 정상 문장 맨 앞에 그대로 들러붙어 등장한다
# ("Display comment 정형외과에서 진료를 받아보시는 것도 고려해볼 수 있습니다." -
# 뒤에 이어지는 문장 자체는 정상 내용). 문장을 통째로 지우면 안 되므로(뒷부분이
# 정상 내용), 라벨 부분만 벗겨낸다. "영문 단어 뒤에 한글이 오면 지운다" 같은 일반
# 정규식은 "MRI 검사를"처럼 정당한 의학 약어까지 지워버릴 위험이 있어서, 실제
# 관찰된 정확한 문자열만 좁게 제거한다(오탐보다 누락이 안전한 방향).
_KNOWN_LEADING_LABEL_PHRASES = ("Display comment ", "DisplayName ", "Example Response ")


def _strip_known_label_phrases(text: str) -> str:
    for phrase in _KNOWN_LEADING_LABEL_PHRASES:
        text = text.replace(phrase, "")
    return text


@lru_cache(maxsize=1)
def _system_prompt_leak_fragments() -> tuple[str, ...]:
    from .prompt_builder import _load_system_prompt  # 지연 import - 순환참조 방지

    fragments: set[str] = set(_KNOWN_NON_PROMPT_LEAK_MARKERS)
    for line in _load_system_prompt().split("\n"):
        for piece in re.split(r"(?<=[.!?])\s+", line):
            piece = piece.strip("-•# \t")
            if len(piece) >= _MIN_PROMPT_LEAK_MATCH_CHARS:
                fragments.add(piece)
    # 긴 조각부터 찾아야 짧은 조각(다른 긴 조각의 일부일 수 있음) 때문에 절단
    # 지점이 실제보다 늦게(뒤로) 잡히는 걸 방지한다.
    return tuple(sorted(fragments, key=len, reverse=True))


def _strip_system_prompt_echo(text: str) -> str:
    earliest: int | None = None
    for fragment in _system_prompt_leak_fragments():
        idx = text.find(fragment)
        if idx != -1 and (earliest is None or idx < earliest):
            earliest = idx
    if earliest is None:
        return text
    return text[:earliest].rstrip()


# 실제 관찰된 사례 - 정상적인 첫 문단을 낸 뒤, 모델이 그 문단 전체(또는 그
# 앞부분)를 "모델 답변:" 같은 라벨과 함께, 그 사이에 다른 언어 가비지까지 섞어가며
# 여러 번 다시 출력했다. max_output_tokens에 걸려 마지막 반복이 중간에 잘리기도
# 해서(이전 반복들과 글자 수가 달라짐), 끝에서부터 "완전히 같은 줄"을 찾는
# `_strip_trailing_repeated_lines`가 못 잡는다(마지막 조각이 앞선 반복과 정확히
# 일치하지 않음). 그래서 "첫 문단이 문자열 앞부분만이라도 나중에 다시 등장하면"
# 그 순간 이후로는(사이에 낀 다른 가비지까지 포함해서) 전부 버리고 첫 문단만
# 남긴다 - 문단 하나짜리 답변에서 반복이 시작되면 그 이후 전부가 신뢰할 수 없는
# 상태라고 보는 것이 안전하다.
_MIN_SELF_REPEAT_ANCHOR_CHARS = 20


def _strip_after_answer_repeats_itself(text: str) -> str:
    lines = text.split("\n")
    non_blank_indices = [i for i, line in enumerate(lines) if line.strip()]
    if not non_blank_indices:
        return text

    anchor_idx = non_blank_indices[0]
    anchor = lines[anchor_idx].strip()
    if len(anchor) < _MIN_SELF_REPEAT_ANCHOR_CHARS:
        return text  # 첫 줄이 너무 짧으면(인사말 등) 비교 근거로 못 씀 - 오탐 방지
    anchor_prefix = anchor[:_MIN_SELF_REPEAT_ANCHOR_CHARS]

    for idx in non_blank_indices[1:]:
        candidate = lines[idx].strip()
        if candidate == anchor or candidate[:_MIN_SELF_REPEAT_ANCHOR_CHARS] == anchor_prefix:
            return "\n".join(lines[: anchor_idx + 1]).rstrip()
    return text


# 실제 관찰된 사례 - 정상적으로 완결된 문장 뒤에 새 줄로 뜬금없는 짧은 단어
# 하나가 덧붙는 경우가 여러 형태로 있었다("...고려해볼 수 있습니다.\n Hakim"
# 처럼 라틴 문자, "...등)\n견적"처럼 문맥과 무관한 한국어 단어까지). 의학
# 약어(MRI, CT 등)를 위해 라틴 문자는 항상 "허용 문자"로 쳐줘서
# `_strip_trailing_foreign_language_lines`가 라틴 문자 조각을 못 잡고, 한국어
# 단어는 애초에 "외국어 유출"이 아니라서 그 필터의 대상이 아니다. "한글이냐
# 아니냐"가 아니라 "문장을 제대로 끝맺는 형태냐"로 판단한다 - 정상적인 한국어
# 마무리는 거의 항상 종결어미(다/요/죠/까)나 문장부호로 끝나는데("감사합니다.",
# "그런가요?"), "견적"처럼 명사 하나만 뚝 떨어진 조각은 그렇지 않다. 짧고(15자
# 이하) 이런 형태로 안 끝나는 마지막 줄이, 이미 마침표로 끝난 문장 바로 뒤에
# 붙어 있으면 군더더기로 보고 지운다.
_MAX_ORPHAN_TAIL_CHARS = 15
_SENTENCE_FINAL_ENDINGS = (".", "!", "?", ")", "다", "요", "죠", "까")


def _strip_short_orphan_tail(text: str) -> str:
    lines = text.split("\n")
    non_blank_indices = [i for i, line in enumerate(lines) if line.strip()]
    if len(non_blank_indices) < 2:
        return text

    last_idx = non_blank_indices[-1]
    prev_idx = non_blank_indices[-2]
    last_line = lines[last_idx].strip()
    prev_line = lines[prev_idx].strip()

    if len(last_line) > _MAX_ORPHAN_TAIL_CHARS:
        return text
    if last_line.endswith(_SENTENCE_FINAL_ENDINGS):
        return text  # 정상적으로 끝맺는 짧은 마무리 문장(감사합니다 등) - 안 지움
    if not prev_line.endswith((".", "!", "?", ")")):
        return text  # 앞 문장이 이미 완결돼 있을 때만("...등)"처럼 괄호로 끝나는
        # 경우도 포함) "군더더기"로 판단
    return "\n".join(lines[:last_idx]).rstrip()


# 진료과 힌트 라벨("참고용 진료과 정보")을 모델이 괄호/중괄호로 감싸서 문장 맨
# 앞에 그대로 갖다 붙이는 경우가 관찰됐다("{참고용 진료과 정보} 정형외과에서
# 진료를..."). `_unwrap_trailing_department_parenthetical`는 "답변 맨 끝이
# 통째로 괄호로 감싸진" 경우만 잡아서, 문장 앞쪽에 라벨만 괄호로 감싼 이 패턴은
# 못 잡는다. prompt_builder.py가 실제로 쓰는 힌트 라벨 문구를 알고 있으므로,
# 괄호/중괄호로 감싼 형태로 등장하면 그 라벨 부분만 벗겨내고 뒤따르는 문장은
# 그대로 둔다.
_DEPARTMENT_HINT_LABEL_PATTERN = re.compile(r"[({]\s*참고용\s*진료과\s*정보\s*[)}]\s*")


def _strip_wrapped_department_hint_label(text: str) -> str:
    return _DEPARTMENT_HINT_LABEL_PATTERN.sub("", text)


def _contains_risky_dosage(text: str) -> bool:
    return any(pattern.search(text) for pattern in _RISKY_DOSAGE_PATTERNS)


# 실제 관찰된 사례(2026-09, 라이브 테스트) - 의료 답변 없이 모델 스스로에게 주는 것
# 같은 메타 지시문만 출력한 경우가 있었다("답변 완료 후에는 새로운 프롬프트와 함께
# 다시 시작하십시오. 감사합니다! (아무것도 없으므로 그냥 넘어갈게요.) 입니다."). 이
# 위의 다른 필터들은 전부 "정상 답변 뒤에 붙은 꼬리"만 잘라내는데, 이 경우는 답변
# 전체가 의료 정보를 전혀 담고 있지 않아서 잘라낼 "정상 앞부분"이 없다. 그래서 이
# 신호가 발견되면 잘라내지 않고 답변 전체를 빈 문자열로 만들어서, 호출하는 쪽
# (pipeline.py)이 FALLBACK_ANSWER로 대체하게 한다. 오탐(정상 답변을 통째로 날리는
# 것)이 다른 어떤 필터보다 위험하므로, 실제 관찰된 정확한 표현으로만 좁게 잡는다 -
# 새 사례가 나오면 신호를 조심스럽게 추가할 것.
_NON_ANSWER_SIGNALS = (
    "새로운 프롬프트와 함께 다시 시작",
    "그냥 넘어갈게요",
)


def _looks_like_non_answer(text: str) -> bool:
    return any(signal in text for signal in _NON_ANSWER_SIGNALS)


def extract_mentioned_department(answer: str) -> str | None:
    """검증이 끝난 최종 답변에서 LLM이 실제로 언급한 진료과를 찾는다.

    사전 분류(classifier.py)는 사용자의 원문 증상 표현(짧고 표현이 제각각)만
    보고 LLM 호출 *전에* 미리 추측하는 것이라 한계가 뚜렷하다 - 반면 LLM은
    RAG 참고자료까지 다 반영해서 최종 판단을 답변에 자연어로 녹여 쓰므로, 이미
    나온 결과를 그대로 읽는 이 방식이 사전 분류보다 신호가 더 강하다
    (pipeline.py가 사전 분류 결과가 없을 때만 이걸로 보완한다).

    답변에 진료과명이 정확히 하나만 등장하면 그걸 반환한다. 하나도 없거나
    (모델이 진료과를 언급 안 함) 서로 다른 이름이 여러 개 섞여 있으면(모델이
    헷갈려서 진료과를 잘못 여러 개 나열한 경우 - 실제 관찰된 사례) 어느 쪽도
    확신할 근거가 없으므로 None을 반환한다 - 잘못된 확신보다 미분류가 낫다.

    "순환기내과"처럼 일반 진료과 이름("내과")을 부분 문자열로 포함하는 이름이 있어서,
    답변에 "순환기내과"만 언급돼도 substring 매칭으로는 "내과"와 "순환기내과"가 둘 다
    걸려 (실제로는 명확한 언급인데도) 모호한 것으로 오판할 수 있었다 - 더 구체적인
    (긴) 이름이 함께 걸리면 그 안에 포함된 일반 이름은 제외하고 구체적인 쪽만 남긴다."""
    mentioned = {name for name in _DEPARTMENT_NAMES if name in answer}
    specific = {
        name for name in mentioned
        if not any(name != other and name in other for other in mentioned)
    }
    if len(specific) == 1:
        return next(iter(specific))
    return None


def validate(answer: str, *, user_question: str = "") -> str:
    """위험한 패턴이 없으면 원문 그대로 반환한다. 면책 문구는 여기서 붙이지 않는다
    (그건 pipeline.py의 책임 — 이 함수는 LLM 원문 자체만 검증한다).

    `user_question`: "사용자가 입력한 언어로 답변" 정책(한/영/일/중 지원)에 맞춰
    외국어 유출 검사의 허용 문자 범위를 사용자 입력 언어에 맞게 조정하는 데
    쓴다. 안 넘기면(기본값 "") 빈 문자열이 언어 감지에서 한국어로 fallback되어
    기존 동작(한국어 기준 검사)과 동일하게 작동한다 — 호출부가 없어도 안 깨짐."""
    input_language = _detect_input_language(user_question)
    answer = _strip_special_tokens(answer)
    # 아래 두 개는 "끝에서부터 X면 지운다"는 다른 필터들과 달리 텍스트 앞쪽부터
    # 훑어서 위험 신호를 찾고 그 지점부터 통째로 잘라내는 넓은 그물이라, 뒤이은
    # 좁은 필터들이 이미 잘려나간 짧은 텍스트만 상대하도록 먼저 돌린다.
    answer = _strip_system_prompt_echo(answer)
    answer = _strip_after_answer_repeats_itself(answer)
    answer = _strip_known_label_phrases(answer)
    answer = _strip_from_unclosed_code_fence(answer)
    answer = _strip_markdown_syntax(answer)
    answer = _strip_self_generated_disclaimer(answer)
    answer = _strip_trailing_repeated_lines(answer)
    answer = _strip_trailing_inline_repetition(answer)
    answer = _strip_trailing_json_block(answer)
    answer = _strip_trailing_label_leak(answer)
    answer = _strip_trailing_role_strings(answer)
    answer = _strip_trailing_foreign_language_lines(answer, input_language)
    answer = _strip_short_orphan_tail(answer)
    answer = _strip_wrapped_department_hint_label(answer)
    answer = _unwrap_trailing_department_parenthetical(answer)
    if _looks_like_non_answer(answer):
        return ""
    if _contains_risky_dosage(answer):
        return answer + _DOSAGE_WARNING
    return answer
