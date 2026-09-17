import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.core.email_config import email_settings
from app.core.logging import get_logger
from app.repositories.signup import SignupRepository
from app.schemas.signup import MessageResponse
from app.services.email import email_service

password_hash = PasswordHash.recommended()
logger = get_logger("services.signup")


class SignupService:
    def __init__(self, db: Session) -> None:
        self.repository = SignupRepository(db)

    def signup(self, email: str, password: str) -> MessageResponse:
        normalized_email = email.lower().strip()
        if self.repository.find_user_by_email(normalized_email):
            logger.warning("회원가입 실패 (이메일 중복): email=%s", normalized_email)
            raise HTTPException(status.HTTP_409_CONFLICT, "이미 가입된 이메일입니다.")
        self.repository.create_user(normalized_email, password_hash.hash(password))
        code = self._issue_code(normalized_email)
        self.repository.commit()
        sent = email_service.send_verification_code(normalized_email, code)
        return MessageResponse(
            message="인증 코드를 이메일로 발송했습니다.",
            dev_verification_code=None if sent or email_settings.app_env == "production" else code,
        )

    def _issue_code(self, email: str) -> str:
        code = f"{secrets.randbelow(1_000_000):06d}"
        expires_at = datetime.now(UTC) + timedelta(
            minutes=email_settings.email_verification_expire_minutes
        )
        self.repository.replace_verification_code(email, code, expires_at)
        return code
