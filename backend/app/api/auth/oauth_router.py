"""Google/GitHub 소셜 로그인 라우트.

두 개로 나뉜 이유(둘 다 이 파일에 있지만 main.py에서 서로 다른 곳에 마운트됨):
- `oauth_start_router`: "로그인 시작" - 프론트가 부르는 일반 API라
  `/api/auth/oauth/{provider}/authorize`로 다른 auth 엔드포인트와 나란히 둔다.
- `oauth_callback_router`: Google/GitHub가 리다이렉트로 호출하는 콜백 - Google/GitHub
  콘솔에 등록한 redirect_uri(프론트 콜백 라우트가 백엔드로 전달)와 경로가 정확히
  같아야 해서, /api 접두사 없이 main.py가 루트에 직접 마운트한다
  (/auth/google/callback, /oauth/github/callback - 두 provider의 경로 규칙이
  다른 건 이미 각 콘솔에 등록해버린 값을 그대로 따른 것).
"""
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.services.oauth import (
    build_github_authorize_url,
    build_google_authorize_url,
    generate_state,
    login_with_oauth,
    verify_state,
)

logger = get_logger("api.oauth")

oauth_start_router = APIRouter()
oauth_callback_router = APIRouter()


def _oauth_callback_page_url(query: str) -> str:
    # FRONTEND_URL이 끝에 "/"를 붙여 쓰는 경우(.env 관례상 둘 다 있음)와 안 붙이는
    # 경우가 섞여 있어서, 그대로 이어붙이면 "//oauth-callback"처럼 슬래시가 두 번
    # 되어 React Router가 라우트를 못 찾는 문제가 실제로 있었다(2026-09-03) -
    # 여기서 한 번만 정규화한다.
    base = settings.frontend_url.rstrip("/")
    return f"{base}/oauth-callback?{query}"


@oauth_start_router.get("/{provider}/authorize")
def start_oauth_login(provider: str) -> RedirectResponse:
    state = generate_state()
    if provider == "google":
        url = build_google_authorize_url(state)
    elif provider == "github":
        url = build_github_authorize_url(state)
    else:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "지원하지 않는 로그인 방식입니다.")
    return RedirectResponse(url)


def _finish_oauth_callback(
    db: Session, provider: str, code: str | None, state: str | None, error: str | None
) -> RedirectResponse:
    """콜백 처리 공통 로직 - 성공/실패 둘 다 프론트로 리다이렉트한다(사용자가
    Google/GitHub 화면에 그대로 머무르면 안 되므로, 원문 API 에러 응답 대신 항상
    프론트 페이지로 보낸다 - 그래서 아래에서 발생 가능한 HTTPException을 전부
    잡아서 에러 메시지를 쿼리 파라미터로 바꿔 리다이렉트한다). 성공 시 토큰도
    쿼리 파라미터로 싣는다 - access_token이 URL에 남는 게 이상적이진 않지만
    (브라우저 히스토리), 이 프로젝트가 이미 쓰는 짧은 수명의 JWT라 위험이
    제한적이고, 프론트가 /oauth-callback에서 받자마자 저장하고 히스토리를
    replace하도록 만든다."""
    if error:
        logger.info("%s OAuth 콜백 - 사용자가 거부하거나 provider 오류: %s", provider, error)
        return RedirectResponse(_oauth_callback_page_url("error=cancelled"))
    if not code or not state:
        return RedirectResponse(_oauth_callback_page_url("error=invalid_request"))

    try:
        verify_state(state)
        result = login_with_oauth(db, provider, code)
    except HTTPException as exc:
        logger.warning("%s OAuth 콜백 실패: %s", provider, exc.detail)
        return RedirectResponse(_oauth_callback_page_url(f"error={quote(str(exc.detail))}"))

    return RedirectResponse(_oauth_callback_page_url(f"token={result.access_token}"))


@oauth_callback_router.get("/auth/google/callback")
def google_callback(
    db: Annotated[Session, Depends(get_db)],
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    return _finish_oauth_callback(db, "google", code, state, error)


@oauth_callback_router.get("/oauth/github/callback")
def github_callback(
    db: Annotated[Session, Depends(get_db)],
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    return _finish_oauth_callback(db, "github", code, state, error)
