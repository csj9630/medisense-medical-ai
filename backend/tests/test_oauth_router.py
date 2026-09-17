import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app
from app.schemas.auth import LoginResponse, UserResponse


class OAuthRouterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app()
        self.client = TestClient(self.app, follow_redirects=False)

    def test_google_authorize_redirects_to_google_with_configured_client_id(self) -> None:
        with (
            patch.object(settings, "google_client_id", "test-google-id"),
            patch.object(settings, "google_oauth_redirect_uri", "http://localhost:8000/auth/google/callback"),
        ):
            response = self.client.get("/api/auth/oauth/google/authorize")

        self.assertEqual(response.status_code, 307)
        location = response.headers["location"]
        self.assertTrue(location.startswith("https://accounts.google.com/o/oauth2/v2/auth"))
        self.assertIn("client_id=test-google-id", location)

    def test_github_authorize_redirects_to_github(self) -> None:
        with patch.object(settings, "github_client_id", "test-gh-id"):
            response = self.client.get("/api/auth/oauth/github/authorize")

        self.assertEqual(response.status_code, 307)
        self.assertTrue(response.headers["location"].startswith("https://github.com/login/oauth/authorize"))

    def test_unknown_provider_returns_404(self) -> None:
        response = self.client.get("/api/auth/oauth/facebook/authorize")
        self.assertEqual(response.status_code, 404)

    # --- 콜백: 실제로 관찰된 "//oauth-callback" 이중 슬래시 버그(2026-09-03)의 회귀 테스트 ---

    def test_callback_redirect_has_no_double_slash_when_frontend_url_has_trailing_slash(self) -> None:
        with patch.object(settings, "frontend_url", "http://localhost:5173/"):
            response = self.client.get("/auth/google/callback?error=access_denied")

        self.assertEqual(response.headers["location"], "http://localhost:5173/oauth-callback?error=cancelled")

    def test_callback_redirect_works_when_frontend_url_has_no_trailing_slash(self) -> None:
        with patch.object(settings, "frontend_url", "http://localhost:5173"):
            response = self.client.get("/auth/google/callback?error=access_denied")

        self.assertEqual(response.headers["location"], "http://localhost:5173/oauth-callback?error=cancelled")

    def test_callback_missing_code_redirects_with_invalid_request_error(self) -> None:
        with patch.object(settings, "frontend_url", "http://localhost:5173"):
            response = self.client.get("/auth/google/callback?state=abc")

        self.assertEqual(response.headers["location"], "http://localhost:5173/oauth-callback?error=invalid_request")

    def test_successful_callback_redirects_with_token(self) -> None:
        fake_result = LoginResponse(
            access_token="fake-jwt",
            user=UserResponse(
                id="u1", email="a@example.com", profile_image_url=None,
                is_email_verified=True, is_admin=False, created_at=None, has_password=False,
            ),
        )
        with (
            patch.object(settings, "frontend_url", "http://localhost:5173"),
            patch("app.api.auth.oauth_router.verify_state"),
            patch("app.api.auth.oauth_router.login_with_oauth", return_value=fake_result),
        ):
            response = self.client.get("/auth/google/callback?code=abc&state=xyz")

        self.assertEqual(response.headers["location"], "http://localhost:5173/oauth-callback?token=fake-jwt")

    def test_github_callback_path_matches_registered_redirect_uri(self) -> None:
        # /oauth/github/callback - Google과 경로 규칙이 다르지만 각 콘솔에 이미
        # 등록된 값이라 그대로 맞춰야 한다(하나라도 다르면 provider가 거부함).
        with patch.object(settings, "frontend_url", "http://localhost:5173"):
            response = self.client.get("/oauth/github/callback?error=access_denied")

        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "http://localhost:5173/oauth-callback?error=cancelled")


if __name__ == "__main__":
    unittest.main()
