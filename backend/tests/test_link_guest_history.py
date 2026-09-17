import unittest
from unittest.mock import MagicMock

from app.core.config import settings
from app.services.auth import AuthService, create_access_token


class LinkGuestHistoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = AuthService(MagicMock())
        self.service.repository = MagicMock()
        self.service.conversations = MagicMock()
        self.service.consultation_logs = MagicMock()
        self.real_user = MagicMock(id="real-user-id")

    def _guest_user(self, *, user_id: str = "guest-user-id", auth_provider: str = "guest") -> MagicMock:
        return MagicMock(id=user_id, auth_provider=auth_provider)

    def test_moves_conversations_and_logs_then_deletes_guest_user(self) -> None:
        guest_user = self._guest_user()
        self.service.repository.find_user_by_id.return_value = guest_user
        self.service.conversations.reassign_owner.return_value = 3
        guest_token = create_access_token(guest_user.id, settings.guest_token_expire_minutes)

        moved = self.service.link_guest_history(self.real_user, guest_token)

        self.assertEqual(moved, 3)
        self.service.conversations.reassign_owner.assert_called_once_with(
            from_user_id=guest_user.id, to_user_id=self.real_user.id
        )
        self.service.consultation_logs.reassign_owner.assert_called_once_with(
            from_user_id=guest_user.id, to_user_id=self.real_user.id
        )
        self.service.repository.delete_user.assert_called_once_with(guest_user)

    def test_invalid_token_is_ignored_silently(self) -> None:
        moved = self.service.link_guest_history(self.real_user, "not-a-real-jwt")

        self.assertEqual(moved, 0)
        self.service.conversations.reassign_owner.assert_not_called()
        self.service.repository.delete_user.assert_not_called()

    def test_expired_token_is_ignored_silently(self) -> None:
        guest_user = self._guest_user()
        self.service.repository.find_user_by_id.return_value = guest_user
        expired_token = create_access_token(guest_user.id, expire_minutes=-1)

        moved = self.service.link_guest_history(self.real_user, expired_token)

        self.assertEqual(moved, 0)
        self.service.conversations.reassign_owner.assert_not_called()

    def test_token_belonging_to_non_guest_user_is_rejected(self) -> None:
        # 게스트가 아닌(auth_provider != 'guest') 다른 사용자의 토큰을 guest_token
        # 자리에 넣어서 그 사람의 대화를 가로채려는 시도를 막는다 - 핵심 보안 검증.
        other_real_user = self._guest_user(user_id="other-real-user-id", auth_provider="local")
        self.service.repository.find_user_by_id.return_value = other_real_user
        token = create_access_token(other_real_user.id, settings.access_token_expire_minutes)

        moved = self.service.link_guest_history(self.real_user, token)

        self.assertEqual(moved, 0)
        self.service.conversations.reassign_owner.assert_not_called()
        self.service.repository.delete_user.assert_not_called()

    def test_guest_user_not_found_is_ignored_silently(self) -> None:
        self.service.repository.find_user_by_id.return_value = None
        token = create_access_token("deleted-guest-id", settings.guest_token_expire_minutes)

        moved = self.service.link_guest_history(self.real_user, token)

        self.assertEqual(moved, 0)
        self.service.conversations.reassign_owner.assert_not_called()

    def test_same_user_as_current_user_is_a_no_op(self) -> None:
        # 이론상 있으면 안 되는 경우(게스트 토큰이 곧 현재 로그인한 계정)지만,
        # 자기 자신에게 재배정/자기 계정을 삭제하는 사고를 막는 방어선이다.
        token = create_access_token(self.real_user.id, settings.guest_token_expire_minutes)
        self.service.repository.find_user_by_id.return_value = self._guest_user(
            user_id=self.real_user.id
        )

        moved = self.service.link_guest_history(self.real_user, token)

        self.assertEqual(moved, 0)
        self.service.repository.delete_user.assert_not_called()


if __name__ == "__main__":
    unittest.main()
