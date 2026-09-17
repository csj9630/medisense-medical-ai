from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.generated import Users


class PasswordResetRepository:
    """비밀번호 재설정에 필요한 사용자 조회와 저장만 담당합니다."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def find_by_email(self, email: str) -> Users | None:
        return self.db.scalar(select(Users).where(Users.email == email))

    def find_by_id(self, user_id: str) -> Users | None:
        return self.db.get(Users, UUID(user_id))

    def save(self) -> None:
        self.db.commit()
