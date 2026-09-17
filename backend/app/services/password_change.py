from fastapi import HTTPException, status
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.models.generated import Users
from app.repositories.password_change import PasswordChangeRepository
from app.schemas.password_change import ChangePasswordResponse

password_hash = PasswordHash.recommended()


class PasswordChangeService:
    """현재 비밀번호를 검증한 후 새 비밀번호를 안전하게 저장합니다."""

    def __init__(self, db: Session) -> None:
        self.repository = PasswordChangeRepository(db)

    def change(self, user: Users, current_password: str, new_password: str) -> ChangePasswordResponse:
        # 소셜 로그인/게스트 계정은 애초에 비밀번호가 없다 - "틀렸다"가 아니라
        # "없다"는 걸 정확히 알려준다(프론트는 이 케이스에선 아예 버튼을 안 보여주니,
        # 여기 닿는 건 API를 직접 호출하는 경우뿐이다).
        if not user.password_hash:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "소셜 로그인 계정은 비밀번호가 없습니다.")
        if not password_hash.verify(current_password, user.password_hash):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "현재 비밀번호가 올바르지 않습니다.")
        if password_hash.verify(new_password, user.password_hash):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "새 비밀번호는 현재 비밀번호와 달라야 합니다.")

        self.repository.save_password(user, password_hash.hash(new_password))
        return ChangePasswordResponse(message="비밀번호가 변경됐습니다.")
