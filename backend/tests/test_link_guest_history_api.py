import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.auth.dependencies import get_current_user
from app.core.database import get_db
from app.main import app


class LinkGuestHistoryApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id="real-user-id",
            auth_provider="local",
        )
        app.dependency_overrides[get_db] = lambda: object()
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)

    def test_returns_moved_conversation_count(self) -> None:
        with patch("app.api.auth.router.AuthService") as service_cls:
            service_cls.return_value.link_guest_history.return_value = 2

            response = self.client.post(
                "/api/auth/link-guest-history",
                json={"guest_token": "cached-guest-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"linked_conversation_count": 2})
        service_cls.return_value.link_guest_history.assert_called_once()
        args = service_cls.return_value.link_guest_history.call_args.args
        self.assertEqual(args[1], "cached-guest-token")

    def test_requires_authentication(self) -> None:
        app.dependency_overrides.pop(get_current_user, None)
        try:
            response = self.client.post(
                "/api/auth/link-guest-history",
                json={"guest_token": "anything"},
            )
            self.assertEqual(response.status_code, 401)
        finally:
            app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
                id="real-user-id",
                auth_provider="local",
            )


if __name__ == "__main__":
    unittest.main()
