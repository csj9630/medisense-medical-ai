from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.auth.dependencies import get_current_user
from app.core.database import get_db
from app.models.generated import Users
from app.schemas.auth import (
    DeleteAccountRequest,
    DeleteAccountResponse,
    DeleteConsultationsResponse,
    UsageSummaryResponse,
)
from app.services.mypage import MyPageService

router = APIRouter()


@router.get("/me/usage", response_model=UsageSummaryResponse)
def usage_summary(
    current_user: Annotated[Users, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> UsageSummaryResponse:
    return MyPageService(db).usage_summary(current_user)


@router.delete("/me", response_model=DeleteAccountResponse)
def delete_account(
    payload: DeleteAccountRequest,
    current_user: Annotated[Users, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> DeleteAccountResponse:
    return MyPageService(db).delete_account(current_user, payload.password)


@router.delete("/me/consultations", response_model=DeleteConsultationsResponse)
def delete_all_consultations(
    current_user: Annotated[Users, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> DeleteConsultationsResponse:
    return MyPageService(db).delete_all_consultations(current_user)
