"""텍스트 청킹 — 문장 경계를 유지하며 '토큰' 예산 단위로 자르고, 청크 사이를 겹친다(overlap).

글자 수 대신 토큰 수를 쓰는 이유: 임베딩 모델이 실제로 소비하는 단위는 토큰이고,
한국어는 영어와 달리 글자 수 대비 토큰 수가 안정적이지 않아서(음절/서브워드 분리가
토크나이저마다 다름) 글자 수 기준 예산은 모델이 보는 것과 어긋난다.

**어떤 토크나이저를 쓰는가**: 특정 임베딩 모델의 토크나이저를 쓰지 않는다 — 임베딩
모델은 팀원이 별도로 정하는 중이라(`ai/rag/embeddings/` 참고), 청킹이 특정 모델에
묶이면 모델이 바뀔 때마다 청킹도 다시 검증해야 한다. 대신 범용 토크나이저(tiktoken)로
"대략 이 정도 토큰 예산"만 맞춘다 — 실제 임베딩 모델의 토큰 수와 정확히 일치하진
않지만, 청킹 목적(예산을 벗어나는 거대 청크를 안 만드는 것)에는 이 정도 근사로 충분하다.

그 외 두 가지 안전장치:
- 문장 하나가 이미 예산을 넘으면(OCR로 뽑은 표/양식처럼 문장부호 없는 덩어리 텍스트)
  그 안에서 토큰 단위로 강제 분할한다 — 안 그러면 쪼개지지 않는 거대 청크가 생긴다.
- 공백뿐이거나 특수문자/기호만 있고 실제 내용(한글/영문/숫자)이 거의 없는 청크는
  버린다 — OCR 오탐지로 생기는 쓰레기 청크가 임베딩/검색 인덱스에 들어가지 않게.
"""
import re
from dataclasses import dataclass
from functools import lru_cache

_SENTENCE_END = re.compile(r"(?<=[.!?。！？])\s+")
# 한글 음절, 영문, 숫자가 하나도 없으면 "의미 있는 내용"이 아니라고 본다.
_MEANINGFUL_CONTENT = re.compile(r"[가-힣a-zA-Z0-9]")
# 빈 줄(단락 구분) 또는 "제N조" 같은 조항 헤딩 앞 — 문장부호와 무관하게 항상 끊어야
# 하는 문맥 경계. 여기서 안 끊으면 토큰 예산만 보고 서로 다른 조항/단락 내용이
# 한 청크에 섞여 들어간다.
_HARD_BOUNDARY = re.compile(r"\n\s*\n+|(?=\n\s*제\s*\d+\s*조)")

TOKENIZER_ENCODING = "cl100k_base"
DEFAULT_MAX_TOKENS = 300
DEFAULT_OVERLAP_TOKENS = 60
MIN_MEANINGFUL_CHARS = 2


@dataclass
class Chunk:
    index: int
    text: str
    token_count: int = 0


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_END.split(text) if s.strip()]


@lru_cache(maxsize=1)
def _get_tokenizer():
    import tiktoken

    return tiktoken.get_encoding(TOKENIZER_ENCODING)


def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_get_tokenizer().encode(text))


def is_garbage(text: str) -> bool:
    """공백뿐이거나, 기호/특수문자만 있고 실제 내용이 거의 없는 청크인지 판단."""
    stripped = text.strip()
    if not stripped:
        return True
    return len(_MEANINGFUL_CONTENT.findall(stripped)) < MIN_MEANINGFUL_CHARS


def _decode_token_slice(tokenizer, ids: list[int]) -> str:
    """토큰 id 리스트의 일부만 잘라 독립적으로 decode하면, 한글처럼 한 글자가 토큰
    여러 개로 인코딩되는 경우 그 경계가 글자 중간에서 잘릴 수 있다 — 이때 깨진
    바이트가 U+FFFD(대체 문자, "�")로 디코딩된다. 정상적인 텍스트는 cleaning.py가
    이미 깨진 유니코드를 걸러서 여기까지 오지 않으므로, 슬라이스 맨 앞/뒤에 남는
    "�"는 실제 내용이 아니라 순수한 토큰 경계 아티팩트다 — 거기서만 제거한다
    (중간에 있으면 원래 있던 내용일 수 있으니 안 건드림)."""
    return tokenizer.decode(ids).strip("�")


def _tail_by_tokens(text: str, n_tokens: int) -> str:
    tokenizer = _get_tokenizer()
    ids = tokenizer.encode(text)
    if len(ids) <= n_tokens:
        return text
    return _decode_token_slice(tokenizer, ids[-n_tokens:])


def _force_split_by_tokens(text: str, max_tokens: int, overlap_tokens: int = 0) -> list[str]:
    """문장부호가 없어 한 덩어리로 묶인 텍스트를 토큰 단위로 강제 분할한다.
    문장 단위 패킹(_pack_sentences)과 똑같이 조각 사이를 overlap_tokens만큼 겹쳐서,
    라벨/값 나열형 OCR 텍스트(이력서, 표 등)처럼 문장부호가 없어 이 경로를 타는
    경우에도 overlap이 무시되지 않게 한다."""
    tokenizer = _get_tokenizer()
    ids = tokenizer.encode(text)
    if len(ids) <= max_tokens:
        return [text]
    step = max(max_tokens - overlap_tokens, 1)  # overlap이 max_tokens 이상이면 최소 1씩은 전진
    pieces = []
    for i in range(0, len(ids), step):
        piece_ids = ids[i : i + max_tokens]
        if not piece_ids:
            break
        pieces.append(_decode_token_slice(tokenizer, piece_ids))
        if i + max_tokens >= len(ids):
            break
    return pieces


def _pack_sentences(sentences: list[str], max_tokens: int, overlap_tokens: int) -> list[str]:
    """문장 리스트를 토큰 예산 안에서 겹쳐가며(overlap) 청크로 묶는다."""
    raw_chunks: list[str] = []
    current = ""
    current_tokens = 0

    for sentence in sentences:
        sentence_tokens = count_tokens(sentence)

        if sentence_tokens > max_tokens:
            if current:
                raw_chunks.append(current)
                current, current_tokens = "", 0
            raw_chunks.extend(_force_split_by_tokens(sentence, max_tokens, overlap_tokens))
            continue

        if current and current_tokens + sentence_tokens > max_tokens:
            raw_chunks.append(current)
            # 다음 청크 앞부분에 이전 청크 끝부분을 겹쳐서 문맥이 뚝 끊기지 않게 한다.
            # decode/재encode 과정에서 토큰 수가 조금 흔들릴 수 있어(BPE 경계 문제),
            # overlap을 붙인 결과가 실제로 예산을 넘으면 이번만 overlap 없이 새로 시작한다
            # — 안 그러면 청크가 예산을 계속 넘는 채로 다음 문장까지 누적된다.
            overlap_text = _tail_by_tokens(current, overlap_tokens)
            candidate = f"{overlap_text} {sentence}".strip()
            candidate_tokens = count_tokens(candidate)
            if candidate_tokens <= max_tokens:
                current, current_tokens = candidate, candidate_tokens
            else:
                current, current_tokens = sentence, sentence_tokens
        else:
            current = f"{current} {sentence}".strip()
            current_tokens += sentence_tokens

    if current:
        raw_chunks.append(current)
    return raw_chunks


def chunk_text(
    text: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[Chunk]:
    # 빈 줄/조항 헤딩 같은 문맥 경계로 먼저 블록을 나누고, 블록별로 독립적으로 토큰
    # 예산 패킹을 돌린다 — 이러면 overlap도 블록 안에서만 걸려서 서로 다른 단락/조항이
    # 한 청크에 섞이거나, 앞 조항 꼬리가 다음 조항 머리에 끼어드는 일이 없다.
    raw_chunks: list[str] = []
    for block in _HARD_BOUNDARY.split(text):
        if not block or not block.strip():
            continue
        # 문장 단위로 거를 때 걸러야 쓰레기 문장이 다른 진짜 문장 사이에 낀 채로 청크에
        # 섞여 들어가는 걸 막는다 — 청크 전체를 보고 거르면 "쓰레기+진짜 내용"이 섞인
        # 청크는 안 걸러진다 (진짜 내용이 있으니 통째로는 "쓰레기"가 아니라서).
        sentences = [s for s in split_sentences(block) if not is_garbage(s)]
        raw_chunks.extend(_pack_sentences(sentences, max_tokens, overlap_tokens))

    meaningful = [c.strip() for c in raw_chunks if not is_garbage(c)]
    return [Chunk(index=i, text=c, token_count=count_tokens(c)) for i, c in enumerate(meaningful)]
