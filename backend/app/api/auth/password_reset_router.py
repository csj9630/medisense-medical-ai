from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.password_reset import (
    ForgotPasswordRequest,
    PasswordResetMessage,
    ResetPasswordRequest,
    ValidateResetTokenRequest,
)
from app.services.password_reset import PasswordResetService

router = APIRouter()


@router.post("/forgot-password", response_model=PasswordResetMessage)
def forgot_password(
    payload: ForgotPasswordRequest,
    db: Annotated[Session, Depends(get_db)],
) -> PasswordResetMessage:
    return PasswordResetService(db).request_reset(payload.email)


@router.post("/reset-password", response_model=PasswordResetMessage)
def reset_password(
    payload: ResetPasswordRequest,
    db: Annotated[Session, Depends(get_db)],
) -> PasswordResetMessage:
    return PasswordResetService(db).reset_password(payload.token, payload.new_password)


@router.post("/validate-reset-token", response_model=PasswordResetMessage)
def validate_reset_token(
    payload: ValidateResetTokenRequest,
    db: Annotated[Session, Depends(get_db)],
) -> PasswordResetMessage:
    return PasswordResetService(db).validate_token(payload.token)
