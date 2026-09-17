import unittest
from unittest.mock import MagicMock

from app.services.auth import AuthService


class CreateGuestSessionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = AuthService(MagicMock())
        self.service.repository = MagicMock()
        self.service.guest_throttle = MagicMock()

    def test_creates_guest_when_ip_is_within_limit(self) -> None:
        self.service.guest_throttle.check_and_increment.return_value = True
        guest_user = MagicMock(
            id="g1", email="guest@x.internal", profile_image_url=None,
            is_email_verified=True, is_admin=False, created_at=None, password_hash=None,
        )
        self.service.repository.create_guest_user.return_value = guest_user

        result = self.service.create_guest_session("203.0.113.9")

        self.service.guest_throttle.check_and_increment.assert_called_once()
        self.service.repository.create_guest_user.assert_called_once()
        self.assertEqual(result.user.id, "g1")

    def test_rejects_when_ip_exceeds_limit(self) -> None:
        self.service.guest_throttle.check_and_increment.return_value = False

        with self.assertRaises(Exception) as ctx:
            self.service.create_guest_session("203.0.113.9")

        self.assertEqual(ctx.exception.status_code, 429)
        self.service.repository.create_guest_user.assert_not_called()

    def test_passes_ip_and_configured_limit_to_throttle_check(self) -> None:
        from app.core.config import settings

        self.service.guest_throttle.check_and_increment.return_value = True
        self.service.repository.create_guest_user.return_value = MagicMock(
            id="g1", email="guest@x.internal", profile_image_url=None,
            is_email_verified=True, is_admin=False, created_at=None, password_hash=None,
        )

        self.service.create_guest_session("198.51.100.2")

        self.service.guest_throttle.check_and_increment.assert_called_once_with(
            "198.51.100.2",
            limit=settings.guest_signup_limit_per_ip,
            window_hours=settings.guest_signup_window_hours,
        )


if __name__ == "__main__":
    unittest.main()
