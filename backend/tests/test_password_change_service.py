import unittest
from unittest.mock import MagicMock

from pwdlib import PasswordHash

from app.services.password_change import PasswordChangeService

_hasher = PasswordHash.recommended()


def _fake_user(**kwargs):
    user = MagicMock()
    for key, value in kwargs.items():
        setattr(user, key, value)
    return user


class PasswordChangeServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = PasswordChangeService(MagicMock())
        self.service.repository = MagicMock()

    def test_oauth_account_gets_clear_no_password_error(self) -> None:
        # "틀렸다"가 아니라 "애초에 비밀번호가 없다"는 걸 정확히 알려줘야 한다
        # (2026-09-03 - 이전엔 소셜 로그인 계정도 "현재 비밀번호가 올바르지
        # 않습니다"로만 나와서 사용자가 오해할 수 있었다).
        oauth_user = _fake_user(password_hash=None)

        with self.assertRaises(Exception) as ctx:
            self.service.change(oauth_user, "anything", "new-password123")

        self.assertIn("소셜 로그인", str(ctx.exception.detail))
        self.service.repository.save_password.assert_not_called()

    def test_wrong_current_password_is_rejected(self) -> None:
        user = _fake_user(password_hash=_hasher.hash("real-password"))

        with self.assertRaises(Exception):
            self.service.change(user, "wrong-password", "new-password123")
        self.service.repository.save_password.assert_not_called()

    def test_new_password_same_as_current_is_rejected(self) -> None:
        user = _fake_user(password_hash=_hasher.hash("real-password"))

        with self.assertRaises(Exception):
            self.service.change(user, "real-password", "real-password")
        self.service.repository.save_password.assert_not_called()

    def test_successful_change_saves_new_hash(self) -> None:
        user = _fake_user(password_hash=_hasher.hash("real-password"))

        self.service.change(user, "real-password", "new-password123")

        self.service.repository.save_password.assert_called_once()
        saved_user, saved_hash = self.service.repository.save_password.call_args[0]
        self.assertIs(saved_user, user)
        self.assertTrue(_hasher.verify("new-password123", saved_hash))


if __name__ == "__main__":
    unittest.main()
