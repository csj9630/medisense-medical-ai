from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.auth.dependencies import get_current_user
from app.core.client_ip import get_client_ip
from app.core.database import get_db
from app.models.generated import Users
from app.schemas.auth import (
    LinkGuestHistoryRequest,
    LinkGuestHistoryResponse,
    LoginRequest,
    LoginResponse,
    UserResponse,
)
from app.services.auth import AuthService, to_user_response

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Annotated[Session, Depends(get_db)]) -> LoginResponse:
    return AuthService(db).login(payload.email, payload.password)


@router.post("/guest", response_model=LoginResponse, status_code=201)
def create_guest_session(request: Request, db: Annotated[Session, Depends(get_db)]) -> LoginResponse:
    """비로그인 사용자가 채팅을 시작할 때 프론트에서 자동으로 호출하는 임시 계정 발급."""
    return AuthService(db).create_guest_session(get_client_ip(request))


@router.get("/me", response_model=UserResponse)
def me(current_user: Annotated[Users, Depends(get_current_user)]) -> UserResponse:
    return to_user_response(current_user)


@router.post("/link-guest-history", response_model=LinkGuestHistoryResponse)
def link_guest_history(
    payload: LinkGuestHistoryRequest,
    current_user: Annotated[Users, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> LinkGuestHistoryResponse:
    """게스트로 대화하다 로그인/회원가입을 마친 직후 프론트가 호출 - 게스트
    계정 명의의 대화 이력을 방금 로그인한 계정으로 옮긴다."""
    moved = AuthService(db).link_guest_history(current_user, payload.guest_token)
    return LinkGuestHistoryResponse(linked_conversation_count=moved)
