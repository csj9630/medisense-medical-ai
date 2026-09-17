"""최근의 완결된 사용자/상담 답변 쌍을 제한된 길이로 보존한다."""

from ai.llm.contracts import LlmMessage

MAX_HISTORY_TURNS = 6
MAX_HISTORY_CHARS = 6000


def select_history(messages: tuple[LlmMessage, ...]) -> tuple[LlmMessage, ...]:
    turns: list[tuple[LlmMessage, LlmMessage]] = []
    pending: LlmMessage | None = None
    for message in messages:
        if message.role == "user":
            pending = message if message.content.strip() else None
        elif message.role == "assistant" and pending is not None:
            if message.content.strip():
                turns.append((pending, message))
            pending = None

    selected: list[tuple[LlmMessage, LlmMessage]] = []
    size = 0
    for turn in reversed(turns[-MAX_HISTORY_TURNS:]):
        turn_size = sum(len(message.content) for message in turn)
        if size + turn_size > MAX_HISTORY_CHARS:
            break
        selected.append(turn)
        size += turn_size
    return tuple(message for turn in reversed(selected) for message in turn)
