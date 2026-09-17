from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.api.auth.dependencies import get_current_user
from app.core.database import get_db
from app.models.generated import Users
from app.schemas.auth import UserResponse
from app.services.auth import to_user_response
from app.services.profile import ProfileService

router = APIRouter()


@router.post("/profile/image", response_model=UserResponse)
async def upload_profile_image(
    file: Annotated[UploadFile, File(...)],
    current_user: Annotated[Users, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> UserResponse:
    user = await ProfileService(db).upload_image(current_user, file)
    return to_user_response(user)
