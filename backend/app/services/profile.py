from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.models.generated import Users
from app.repositories.profile import ProfileRepository
from app.services.r2_storage import r2_storage

ALLOWED_IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MAX_PROFILE_IMAGE_BYTES = 5 * 1024 * 1024


class ProfileService:
    def __init__(self, db: Session) -> None:
        self.repository = ProfileRepository(db)

    async def upload_image(self, user: Users, file: UploadFile) -> Users:
        extension = ALLOWED_IMAGE_TYPES.get(file.content_type or "")
        if not extension:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "JPG, PNG, WEBP 이미지만 업로드할 수 있습니다.")

        content = await file.read(MAX_PROFILE_IMAGE_BYTES + 1)
        if len(content) > MAX_PROFILE_IMAGE_BYTES:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "프로필 이미지는 5MB 이하여야 합니다.")
        if not content:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "빈 파일은 업로드할 수 없습니다.")

        # UUID 파일명으로 사용자 파일명 충돌과 경로 삽입을 방지합니다.
        # pathlib.Path는 쓰지 않는다 — 이건 파일시스템 경로가 아니라 S3/R2 오브젝트
        # 키(그대로 공개 URL에 들어감)라서 항상 "/"여야 하는데, Windows에서 Path는
        # "\"를 쓴다(실제로 이 버그 때문에 프로필 이미지 URL이 다 깨져 있었다).
        key = f"profiles/{user.id}/{uuid4().hex}{extension}"
        try:
            image_url = r2_storage.upload(content, key, file.content_type or "image/jpeg")
        except RuntimeError as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error

        self.repository.save_image_url(user, image_url)
        return user
