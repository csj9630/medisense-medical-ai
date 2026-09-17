from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.signup import (
    MessageResponse,
    SignupRequest,
)
from app.services.signup import SignupService

router = APIRouter()


@router.post("/signup", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db: Annotated[Session, Depends(get_db)]) -> MessageResponse:
    return SignupService(db).signup(payload.email, payload.password)
