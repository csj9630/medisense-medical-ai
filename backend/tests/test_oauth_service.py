import time
import unittest
from unittest.mock import MagicMock, patch

import jwt

from app.core.config import settings
from app.services import oauth
from app.services.oauth import OAuthProfile


class StateTest(unittest.TestCase):
    def test_generated_state_verifies_successfully(self) -> None:
        state = oauth.generate_state()
        oauth.verify_state(state)  # 예외 안 나면 통과

    def test_garbage_state_is_rejected(self) -> None:
        with self.assertRaises(Exception):
            oauth.verify_state("이건-유효한-JWT가-아님")

    def test_expired_state_is_rejected(self) -> None:
        expired = jwt.encode(
            {"nonce": "x", "exp": int(time.time()) - 60},
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        with self.assertRaises(Exception):
            oauth.verify_state(expired)

    def test_state_signed_with_wrong_secret_is_rejected(self) -> None:
        # 다른 비밀키로 서명된 state는(위조 시도) 반드시 걸러야 한다 - CSRF 방어의 핵심.
        forged = jwt.encode({"nonce": "x", "exp": int(time.time()) + 300}, "다른-비밀키", algorithm="HS256")
        with self.assertRaises(Exception):
            oauth.verify_state(forged)


class AuthorizeUrlTest(unittest.TestCase):
    def test_google_url_includes_client_id_and_redirect_uri(self) -> None:
        with (
            patch.object(settings, "google_client_id", "test-client-id"),
            patch.object(settings, "google_oauth_redirect_uri", "https://example.com/cb"),
        ):
            url = oauth.build_google_authorize_url("some-state")
        self.assertIn("client_id=test-client-id", url)
        self.assertIn("state=some-state", url)
        self.assertTrue(url.startswith(oauth.GOOGLE_AUTHORIZE_URL))

    def test_google_url_raises_when_not_configured(self) -> None:
        with patch.object(settings, "google_client_id", None):
            with self.assertRaises(Exception):
                oauth.build_google_authorize_url("state")

    def test_github_url_includes_client_id(self) -> None:
        with (
            patch.object(settings, "github_client_id", "gh-client-id"),
            patch.object(settings, "github_oauth_redirect_uri", "https://example.com/cb"),
        ):
            url = oauth.build_github_authorize_url("some-state")
        self.assertIn("client_id=gh-client-id", url)
        self.assertTrue(url.startswith(oauth.GITHUB_AUTHORIZE_URL))

    def test_github_url_raises_when_not_configured(self) -> None:
        with patch.object(settings, "github_client_id", None):
            with self.assertRaises(Exception):
                oauth.build_github_authorize_url("state")


class LoginWithOauthTest(unittest.TestCase):
    def _fake_user(self, **kwargs):
        user = MagicMock()
        for key, value in kwargs.items():
            setattr(user, key, value)
        return user

    def test_returning_user_matched_by_provider_and_oauth_id_reuses_account(self) -> None:
        db = MagicMock()
        existing_user = self._fake_user(
            id="u1",
            auth_provider="google",
            oauth_id="g-1",
            email="a@example.com",
            profile_image_url=None,
            is_email_verified=True,
            is_admin=False,
            created_at=None,
        )

        with (
            patch(
                "app.services.oauth._fetch_google_profile",
                return_value=OAuthProfile(oauth_id="g-1", email="a@example.com", profile_image_url=None),
            ),
            patch("app.services.oauth.AuthRepository") as mock_repo_cls,
        ):
            mock_repo = mock_repo_cls.return_value
            mock_repo.find_user_by_oauth.return_value = existing_user

            result = oauth.login_with_oauth(db, "google", "auth-code")

        mock_repo.find_user_by_oauth.assert_called_once_with("google", "g-1")
        mock_repo.create_oauth_user.assert_not_called()
        self.assertEqual(result.user.id, "u1")

    def test_new_user_is_created_when_no_existing_match(self) -> None:
        db = MagicMock()
        new_user = self._fake_user(
            id="u2",
            email="new@example.com",
            profile_image_url=None,
            is_email_verified=True,
            is_admin=False,
            created_at=None,
        )

        with (
            patch(
                "app.services.oauth._fetch_github_profile",
                return_value=OAuthProfile(oauth_id="gh-1", email="new@example.com", profile_image_url="http://img"),
            ),
            patch("app.services.oauth.AuthRepository") as mock_repo_cls,
        ):
            mock_repo = mock_repo_cls.return_value
            mock_repo.find_user_by_oauth.return_value = None
            mock_repo.find_user_by_email.return_value = None
            mock_repo.create_oauth_user.return_value = new_user

            oauth.login_with_oauth(db, "github", "auth-code")

        mock_repo.create_oauth_user.assert_called_once_with(
            provider="github", oauth_id="gh-1", email="new@example.com", profile_image_url="http://img"
        )

    def test_links_to_existing_account_with_same_email_from_different_provider(self) -> None:
        # 실제 관찰된 사례(2026-09-03) - 로컬/GitHub로 이미 가입된 이메일로 구글
        # 로그인을 시도하면, 두 방식 다 이메일 소유를 이미 검증했으므로 자동으로
        # 같은 계정에 이어줘야 한다(막으면 본인이 로그인을 못 하게 됨).
        db = MagicMock()
        existing_local_user = self._fake_user(
            auth_provider="local",
            email="taken@example.com",
            profile_image_url=None,
            is_email_verified=True,
            is_admin=False,
            created_at=None,
        )
        linked_user = self._fake_user(
            id="u3",
            email="taken@example.com",
            profile_image_url="http://img",
            is_email_verified=True,
            is_admin=False,
            created_at=None,
        )

        with (
            patch(
                "app.services.oauth._fetch_google_profile",
                return_value=OAuthProfile(oauth_id="g-2", email="taken@example.com", profile_image_url="http://img"),
            ),
            patch("app.services.oauth.AuthRepository") as mock_repo_cls,
        ):
            mock_repo = mock_repo_cls.return_value
            mock_repo.find_user_by_oauth.return_value = None
            mock_repo.find_user_by_email.return_value = existing_local_user
            mock_repo.link_oauth_identity.return_value = linked_user

            oauth.login_with_oauth(db, "google", "auth-code")

        mock_repo.link_oauth_identity.assert_called_once_with(
            existing_local_user, provider="google", oauth_id="g-2", profile_image_url="http://img"
        )
        mock_repo.create_oauth_user.assert_not_called()

    def test_unknown_provider_is_rejected(self) -> None:
        with self.assertRaises(Exception):
            oauth.login_with_oauth(MagicMock(), "facebook", "code")


if __name__ == "__main__":
    unittest.main()
