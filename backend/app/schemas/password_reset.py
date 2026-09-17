from pydantic import BaseModel, EmailStr, Field


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class ValidateResetTokenRequest(BaseModel):
    token: str


class PasswordResetMessage(BaseModel):
    message: str
    # SMTP가 없는 로컬 환경에서만 테스트 링크가 반환됩니다.
    dev_reset_url: str | None = None
