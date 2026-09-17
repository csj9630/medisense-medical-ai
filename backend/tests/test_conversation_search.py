import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

from app.services.conversation import ConversationService


def _fake_conversation(**kwargs):
    conv = MagicMock()
    defaults = dict(
        id=uuid4(), title="제목", is_title_custom=False, category=None, updated_at=datetime.now(UTC),
    )
    defaults.update(kwargs)
    for key, value in defaults.items():
        setattr(conv, key, value)
    return conv


class SearchConversationsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ConversationService(MagicMock())
        self.service.repository = MagicMock()
        self.user_id = uuid4()

    def test_blank_query_falls_back_to_full_list_without_searching(self) -> None:
        self.service.repository.list_by_user.return_value = [_fake_conversation()]

        result = self.service.search_conversations(self.user_id, "   ")

        self.assertEqual(len(result), 1)
        self.service.repository.list_by_user.assert_called_once_with(self.user_id)
        self.service.repository.search.assert_not_called()

    def test_non_blank_query_uses_repository_search_with_stripped_text(self) -> None:
        self.service.repository.search.return_value = [_fake_conversation(title="정형외과 상담")]

        result = self.service.search_conversations(self.user_id, "  어깨  ")

        self.assertEqual(len(result), 1)
        self.service.repository.search.assert_called_once_with(self.user_id, "어깨")
        self.service.repository.list_by_user.assert_not_called()


if __name__ == "__main__":
    unittest.main()
