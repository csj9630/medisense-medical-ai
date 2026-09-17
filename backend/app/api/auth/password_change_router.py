from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.auth.dependencies import get_current_user
from app.core.database import get_db
from app.models.generated import Users
from app.schemas.password_change import ChangePasswordRequest, ChangePasswordResponse
from app.services.password_change import PasswordChangeService

router = APIRouter()


@router.post("/change-password", response_model=ChangePasswordResponse)
def change_password(
    payload: ChangePasswordRequest,
    current_user: Annotated[Users, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ChangePasswordResponse:
    return PasswordChangeService(db).change(
        current_user,
        payload.current_password,
        payload.new_password,
    )
