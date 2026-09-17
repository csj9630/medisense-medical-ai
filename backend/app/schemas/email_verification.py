from pydantic import BaseModel, EmailStr, Field

from app.schemas.signup import MessageResponse


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)


class ResendVerificationRequest(BaseModel):
    email: EmailStr


__all__ = ["MessageResponse", "ResendVerificationRequest", "VerifyEmailRequest"]
