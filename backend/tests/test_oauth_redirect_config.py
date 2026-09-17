import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from app.core.config import Settings
from app.services import oauth


class OAuthRedirectConfigTest(unittest.TestCase):
    def make_settings(self, **kwargs):
        return Settings(
            _env_file=None,
            frontend_url="https://frontend.example/",
            google_client_id="google-test",
            github_client_id="github-test",
            **kwargs,
        )

    def test_both_providers_derive_callback_from_frontend(self):
        for frontend in ("https://frontend.example", "https://frontend.example/"):
            settings = self.make_settings()
            settings.frontend_url = frontend
            with patch.object(oauth, "settings", settings):
                for provider, path in (("google", "/auth/google/callback"), ("github", "/oauth/github/callback")):
                    with self.subTest(frontend=frontend, provider=provider):
                        url = getattr(oauth, f"build_{provider}_authorize_url")("test-state")
                        query = parse_qs(urlparse(url).query)
                        self.assertEqual(query["redirect_uri"], [f"https://frontend.example{path}"])

    def test_explicit_callback_overrides_frontend(self):
        settings = self.make_settings(
            google_oauth_redirect_uri="http://localhost:8000/auth/google/callback",
            github_oauth_redirect_uri="http://localhost:8000/oauth/github/callback",
        )
        self.assertEqual(settings.effective_google_oauth_redirect_uri, settings.google_oauth_redirect_uri)
        self.assertEqual(settings.effective_github_oauth_redirect_uri, settings.github_oauth_redirect_uri)

    def test_blank_callback_uses_frontend(self):
        settings = self.make_settings(google_oauth_redirect_uri="  ", github_oauth_redirect_uri="  ")
        self.assertEqual(settings.effective_google_oauth_redirect_uri, "https://frontend.example/auth/google/callback")
        self.assertEqual(settings.effective_github_oauth_redirect_uri, "https://frontend.example/oauth/github/callback")

    def test_authorization_and_token_exchange_use_identical_redirect_uri(self):
        for provider in ("google", "github"):
            for explicit in ("", "http://localhost:8000/custom-callback"):
                with self.subTest(provider=provider, explicit=explicit):
                    settings = self.make_settings(**{f"{provider}_oauth_redirect_uri": explicit})
                    client = MagicMock()
                    client.post.return_value.status_code = 200
                    client.post.return_value.json.return_value = {"access_token": "provider-token"}
                    client.get.return_value.status_code = 200
                    client.get.return_value.json.return_value = {
                        "sub": "google-user", "id": 1, "email": "test@example.com", "email_verified": True,
                    }
                    with patch.object(oauth, "settings", settings), patch.object(oauth.httpx, "Client") as factory:
                        factory.return_value.__enter__.return_value = client
                        authorize = getattr(oauth, f"build_{provider}_authorize_url")("test-state")
                        getattr(oauth, f"_fetch_{provider}_profile")("test-code")
                    expected = parse_qs(urlparse(authorize).query)["redirect_uri"][0]
                    self.assertEqual(client.post.call_args.kwargs["data"]["redirect_uri"], expected)


if __name__ == "__main__":
    unittest.main()
