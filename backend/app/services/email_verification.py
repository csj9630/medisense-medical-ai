from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.email_config import email_settings
from app.repositories.signup import SignupRepository
from app.schemas.signup import MessageResponse
from app.services.email import email_service
from app.services.signup import SignupService


class EmailVerificationService:
    def __init__(self, db: Session) -> None:
        self.repository = SignupRepository(db)
        self.signup_service = SignupService(db)

    def resend_code(self, email: str) -> MessageResponse:
        normalized_email = email.lower().strip()
        user = self.repository.find_user_by_email(normalized_email)
        if not user:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "가입 정보를 찾을 수 없습니다.")
        if user.is_email_verified:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "이미 인증된 이메일입니다.")
        code = self.signup_service._issue_code(normalized_email)
        self.repository.commit()
        sent = email_service.send_verification_code(normalized_email, code)
        return MessageResponse(
            message="새 인증 코드를 발송했습니다.",
            dev_verification_code=None if sent or email_settings.app_env == "production" else code,
        )

    def verify_email(self, email: str, code: str) -> MessageResponse:
        normalized_email = email.lower().strip()
        verification = self.repository.find_verification(normalized_email, code)
        now = datetime.now(UTC)
        if not verification or verification.expires_at < now:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "인증 코드가 틀렸거나 만료됐습니다.")
        user = self.repository.find_user_by_email(normalized_email)
        if not user:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "가입 정보를 찾을 수 없습니다.")
        user.is_email_verified = True
        verification.verified_at = now
        self.repository.commit()
        return MessageResponse(message="이메일 인증이 완료됐습니다.")
