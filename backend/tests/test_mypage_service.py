import unittest
from unittest.mock import MagicMock

from pwdlib import PasswordHash

from app.services.mypage import MyPageService

_hasher = PasswordHash.recommended()


def _fake_user(**kwargs):
    user = MagicMock()
    for key, value in kwargs.items():
        setattr(user, key, value)
    return user


class DeleteAccountTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = MagicMock()
        self.service = MyPageService(self.db)
        # repository는 실제 DB 접근을 하므로, 여기선 "delete_account가 호출됐는지"만
        # 확인하려고 MagicMock으로 갈아끼운다.
        self.service.repository = MagicMock()

    def test_local_account_requires_correct_password(self) -> None:
        user = _fake_user(password_hash=_hasher.hash("real-password"))

        with self.assertRaises(Exception):
            self.service.delete_account(user, "wrong-password")
        self.service.repository.delete_account.assert_not_called()

    def test_local_account_deletes_with_correct_password(self) -> None:
        user = _fake_user(password_hash=_hasher.hash("real-password"))

        self.service.delete_account(user, "real-password")

        self.service.repository.delete_account.assert_called_once_with(user)

    def test_oauth_account_deletes_without_password(self) -> None:
        # 실제 버그였던 부분(2026-09-03) - 소셜 로그인 계정은 password_hash가
        # 없어서, 이전 코드에서는 항상 "비밀번호가 올바르지 않습니다"로 막혀
        # 탈퇴 자체가 불가능했다.
        oauth_user = _fake_user(password_hash=None)

        self.service.delete_account(oauth_user, None)

        self.service.repository.delete_account.assert_called_once_with(oauth_user)

    def test_guest_account_deletes_without_password(self) -> None:
        guest_user = _fake_user(password_hash=None)

        self.service.delete_account(guest_user, "")

        self.service.repository.delete_account.assert_called_once_with(guest_user)


if __name__ == "__main__":
    unittest.main()
