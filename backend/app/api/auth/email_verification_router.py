from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.email_verification import MessageResponse, ResendVerificationRequest, VerifyEmailRequest
from app.services.email_verification import EmailVerificationService

router = APIRouter()


@router.post("/verify-email", response_model=MessageResponse)
def verify_email(payload: VerifyEmailRequest, db: Annotated[Session, Depends(get_db)]) -> MessageResponse:
    return EmailVerificationService(db).verify_email(payload.email, payload.code)


@router.post("/resend-verification", response_model=MessageResponse)
def resend(payload: ResendVerificationRequest, db: Annotated[Session, Depends(get_db)]) -> MessageResponse:
    return EmailVerificationService(db).resend_code(payload.email)
