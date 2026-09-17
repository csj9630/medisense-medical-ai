from datetime import UTC, datetime, timedelta

import jwt
from fastapi import HTTPException, status
from jwt import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models.generated import Users
from app.repositories.auth import AuthRepository
from app.repositories.consultation_log import ConsultationLogRepository
from app.repositories.conversation import ConversationRepository
from app.repositories.guest_throttle import GuestThrottleRepository
from app.schemas.auth import LoginResponse, UserResponse

password_hash = PasswordHash.recommended()
logger = get_logger("services.auth")


def to_user_response(user: Users) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        email=user.email,
        profile_image_url=user.profile_image_url,
        is_email_verified=bool(user.is_email_verified),
        # DB에 관리자 컬럼이 없는 환경에서는 일반 사용자로 처리합니다.
        is_admin=bool(getattr(user, "is_admin", False)),
        created_at=user.created_at,
        has_password=bool(user.password_hash),
    )


def create_access_token(user_id: str, expire_minutes: int) -> str:
    expires_at = datetime.now(UTC) + timedelta(minutes=expire_minutes)
    return jwt.encode(
        {"sub": user_id, "exp": expires_at},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


class AuthService:
    """회원가입, 인증, 로그인 규칙을 한곳에서 관리합니다."""

    def __init__(self, db: Session) -> None:
        self.repository = AuthRepository(db)
        self.guest_throttle = GuestThrottleRepository(db)
        self.conversations = ConversationRepository(db)
        self.consultation_logs = ConsultationLogRepository(db)

    def login(self, email: str, password: str) -> LoginResponse:
        user = self.repository.find_user_by_email(email.lower().strip())
        if not user or not user.password_hash or not password_hash.verify(password, user.password_hash):
            logger.warning("로그인 실패 (이메일/비밀번호 불일치): email=%s", email)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "이메일 또는 비밀번호가 올바르지 않습니다.")
        if not user.is_email_verified:
            logger.warning("로그인 실패 (이메일 미인증): email=%s", email)
            raise HTTPException(status.HTTP_403_FORBIDDEN, "이메일 인증을 먼저 완료해주세요.")

        token = create_access_token(str(user.id), settings.access_token_expire_minutes)
        return LoginResponse(access_token=token, user=to_user_response(user))

    def create_guest_session(self, client_ip: str) -> LoginResponse:
        """비로그인 사용자가 채팅을 쓸 수 있도록 임시 계정을 발급합니다.

        기존 users/conversations/messages 테이블을 그대로 재사용하고
        auth_provider='guest'로만 구분하므로 스키마 변경이 필요 없다.

        브라우저는 발급받은 토큰을 localStorage에 캐싱해서 재사용하지만, 시크릿창/
        다른 브라우저를 쓰면 매번 새 게스트 계정을 받을 수 있어서
        guest_message_limit을 사실상 무제한으로 우회할 수 있다(완전히 막을 순
        없음 - 익명 사용자라 신원 자체가 없어서). 같은 IP에서 짧은 시간에 새
        게스트 계정을 너무 많이 만드는 것만 제한한다.
        """
        allowed = self.guest_throttle.check_and_increment(
            client_ip,
            limit=settings.guest_signup_limit_per_ip,
            window_hours=settings.guest_signup_window_hours,
        )
        if not allowed:
            logger.warning("게스트 계정 발급 제한 (IP당 한도 초과): ip=%s", client_ip)
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "일시적으로 게스트 계정을 너무 많이 만들었습니다. 잠시 후 다시 시도해주세요.",
            )

        user = self.repository.create_guest_user()
        token = create_access_token(str(user.id), settings.guest_token_expire_minutes)
        return LoginResponse(access_token=token, user=to_user_response(user))

    def link_guest_history(self, current_user: Users, guest_token: str) -> int:
        """게스트로 대화하다 로그인/회원가입한 사용자를 위해, 게스트 계정 명의의
        대화 이력을 방금 로그인한 실제 계정으로 옮긴다.

        guest_token은 프론트가 localStorage에 캐싱해둔 값을 그대로 보내는
        것이라(guestSession.ts) 사용자가 조작 가능한 임의의 문자열일 수 있다 -
        로그인 자체를 막을 이유가 없는 부가 기능이므로, 유효하지 않거나
        의심스러운 경우는 예외를 던지지 않고 조용히 0건으로 처리한다.
        """
        try:
            payload = jwt.decode(
                guest_token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
            )
        except InvalidTokenError:
            return 0

        guest_user_id = payload.get("sub")
        if not guest_user_id:
            return 0

        guest_user = self.repository.find_user_by_id(guest_user_id)
        # auth_provider가 'guest'가 아니면 이관하지 않는다 - 누군가 임의의(혹은
        # 훔친) 다른 사용자의 토큰을 guest_token 자리에 넣어 그 사람의 대화를
        # 가로채는 걸 막기 위한 필수 검증이다.
        if (
            not guest_user
            or guest_user.auth_provider != "guest"
            or guest_user.id == current_user.id
        ):
            return 0

        moved = self.conversations.reassign_owner(
            from_user_id=guest_user.id, to_user_id=current_user.id
        )
        self.consultation_logs.reassign_owner(
            from_user_id=guest_user.id, to_user_id=current_user.id
        )
        # 대화를 다 옮기고 나면 남는 게 없는 임시 계정이라 정리한다(대화/로그
        # 재배정이 먼저 끝난 뒤라 CASCADE로 방금 옮긴 데이터가 같이 지워질 걱정은 없음).
        self.repository.delete_user(guest_user)
        return moved
