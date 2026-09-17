"""Google/GitHub OAuth Authorization Code 플로우.

client_secret을 쓰는 코드 교환은 반드시 서버(여기)에서만 한다 - 프론트에
노출하면 안 된다. state는 서버에 아무 것도 저장하지 않고, 짧은 만료시간을 가진
서명된 JWT를 그대로 state 값으로 써서 CSRF를 막는다(콜백에서 서명 검증만 하면
되므로 세션/DB 저장소가 따로 필요 없다 - access_token 발급과 같은 jwt 라이브러리
재사용).
"""
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import HTTPException, status
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.repositories.auth import AuthRepository
from app.schemas.auth import LoginResponse
from app.services.auth import create_access_token, to_user_response

logger = get_logger("services.oauth")

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"

_HTTP_TIMEOUT = 10.0
_STATE_EXPIRE_MINUTES = 5


@dataclass(frozen=True)
class OAuthProfile:
    oauth_id: str
    email: str
    profile_image_url: str | None


def generate_state() -> str:
    payload = {
        "nonce": secrets.token_urlsafe(16),
        "exp": datetime.now(UTC) + timedelta(minutes=_STATE_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def verify_state(state: str) -> None:
    try:
        jwt.decode(state, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except InvalidTokenError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "로그인 요청이 만료되었거나 유효하지 않습니다.") from error


def build_google_authorize_url(state: str) -> str:
    if not settings.google_client_id:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Google 로그인이 아직 설정되지 않았습니다.")
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.effective_google_oauth_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTHORIZE_URL}?{urlencode(params)}"


def build_github_authorize_url(state: str) -> str:
    if not settings.github_client_id:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "GitHub 로그인이 아직 설정되지 않았습니다.")
    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": settings.effective_github_oauth_redirect_uri,
        "scope": "read:user user:email",
        "state": state,
    }
    return f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"


def _fetch_google_profile(code: str) -> OAuthProfile:
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        token_res = client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.effective_google_oauth_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_res.status_code != 200:
            logger.warning("Google 토큰 교환 실패: %s", token_res.text)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google 로그인에 실패했습니다.")
        access_token = token_res.json().get("access_token")

        userinfo_res = client.get(GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
        if userinfo_res.status_code != 200:
            logger.warning("Google 사용자 정보 조회 실패: %s", userinfo_res.text)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google 로그인에 실패했습니다.")
        data = userinfo_res.json()

    email = data.get("email")
    if not email or not data.get("email_verified"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google 계정의 이메일이 확인되지 않았습니다.")
    return OAuthProfile(oauth_id=str(data["sub"]), email=email, profile_image_url=data.get("picture"))


def _fetch_github_profile(code: str) -> OAuthProfile:
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        token_res = client.post(
            GITHUB_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "redirect_uri": settings.effective_github_oauth_redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        if token_res.status_code != 200:
            logger.warning("GitHub 토큰 교환 실패: %s", token_res.text)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "GitHub 로그인에 실패했습니다.")
        token_payload = token_res.json()
        access_token = token_payload.get("access_token")
        if not access_token:
            logger.warning("GitHub 토큰 응답에 access_token 없음: %s", token_payload)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "GitHub 로그인에 실패했습니다.")

        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"}
        user_res = client.get(GITHUB_USER_URL, headers=headers)
        if user_res.status_code != 200:
            logger.warning("GitHub 사용자 정보 조회 실패: %s", user_res.text)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "GitHub 로그인에 실패했습니다.")
        user_data = user_res.json()

        # GitHub는 프로필 이메일이 비공개면 null로 온다 - user:email scope로 별도
        # 조회해서 primary+verified 이메일을 찾는다.
        email = user_data.get("email")
        if not email:
            emails_res = client.get(GITHUB_EMAILS_URL, headers=headers)
            if emails_res.status_code == 200:
                for entry in emails_res.json():
                    if entry.get("primary") and entry.get("verified"):
                        email = entry.get("email")
                        break

    if not email:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "GitHub 계정에 검증된 이메일이 없습니다. GitHub 설정에서 이메일을 공개하거나 인증해주세요.",
        )
    return OAuthProfile(oauth_id=str(user_data["id"]), email=email, profile_image_url=user_data.get("avatar_url"))


def login_with_oauth(db: Session, provider: str, code: str) -> LoginResponse:
    if provider == "google":
        profile = _fetch_google_profile(code)
    elif provider == "github":
        profile = _fetch_github_profile(code)
    else:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "지원하지 않는 로그인 방식입니다.")

    repo = AuthRepository(db)
    user = repo.find_user_by_oauth(provider, profile.oauth_id)
    if user is None:
        existing_by_email = repo.find_user_by_email(profile.email.lower().strip())
        if existing_by_email is not None:
            # 이미 다른 방식(로컬 비밀번호 또는 다른 provider)으로 가입된 이메일이다 -
            # 자동으로 이어준다. 로컬 회원가입(이메일 인증 필수)과 Google/GitHub(그쪽이
            # 이미 검증한 이메일만 넘겨줌) 전부 "그 이메일의 실제 소유자"임을 이미
            # 증명한 상태라, 같은 이메일이면 같은 사람으로 봐도 안전하다(실제로 본인이
            # Google/GitHub 둘 다 같은 이메일을 쓰는 흔한 경우에 로그인이 막혀서
            # 처음엔 거부했던 게 오히려 더 큰 문제였다 - 2026-09-03 실사용 중 발견).
            logger.info(
                "OAuth 로그인 - 기존 계정(%s)에 %s 연동: %s",
                existing_by_email.auth_provider,
                provider,
                profile.email,
            )
            user = repo.link_oauth_identity(
                existing_by_email,
                provider=provider,
                oauth_id=profile.oauth_id,
                profile_image_url=profile.profile_image_url,
            )
        else:
            user = repo.create_oauth_user(
                provider=provider,
                oauth_id=profile.oauth_id,
                email=profile.email.lower().strip(),
                profile_image_url=profile.profile_image_url,
            )

    token = create_access_token(str(user.id), settings.access_token_expire_minutes)
    return LoginResponse(access_token=token, user=to_user_response(user))
