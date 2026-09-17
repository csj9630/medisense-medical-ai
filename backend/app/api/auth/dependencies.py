from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.generated import Users
from app.repositories.auth import AuthRepository

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> Users:
    """Authorization 헤더의 JWT를 검사해 현재 사용자를 반환합니다."""
    if not credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "로그인이 필요합니다.")
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        user_id = payload.get("sub")
    except InvalidTokenError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "유효하지 않은 로그인 정보입니다.") from error

    user = AuthRepository(db).find_user_by_id(user_id)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "사용자를 찾을 수 없습니다.")
    return user


def require_admin(current_user: Annotated[Users, Depends(get_current_user)]) -> Users:
    """관리자 전용 엔드포인트에 붙이는 의존성 — is_admin이 아니면 403."""
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "관리자 권한이 필요합니다.")
    return current_user
