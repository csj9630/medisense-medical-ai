import unittest

from ai.consultation.history import MAX_HISTORY_CHARS, MAX_HISTORY_TURNS, select_history
from ai.llm.contracts import LlmMessage


class HistoryTest(unittest.TestCase):
    def test_recent_turns_keep_roles_and_order(self):
        messages = tuple(
            message
            for i in range(MAX_HISTORY_TURNS + 2)
            for message in (LlmMessage("user", str(i)), LlmMessage("assistant", f"답변 {i}"))
        )
        self.assertEqual(select_history(messages), messages[4:])

    def test_character_limit_drops_whole_old_turns(self):
        recent = (LlmMessage("user", "어제부터요"), LlmMessage("assistant", "붓기도 있나요?"))
        messages = (LlmMessage("user", "가" * MAX_HISTORY_CHARS), LlmMessage("assistant", "답변"), *recent)
        self.assertEqual(select_history(messages), recent)

    def test_ignores_system_orphan_and_attachment_only_turns(self):
        recent = (LlmMessage("user", "허리가 아파요"), LlmMessage("assistant", "언제부터인가요?"))
        messages = (
            LlmMessage("system", "저장된 지시"),
            LlmMessage("assistant", "짝이 없는 답변"),
            LlmMessage("user", "실패한 요청"),
            LlmMessage("user", ""),
            LlmMessage("assistant", "첨부 안내"),
            *recent,
            LlmMessage("user", "아직 답변이 없는 요청"),
        )
        self.assertEqual(select_history(messages), recent)
