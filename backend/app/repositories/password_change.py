from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.generated import Users


class PasswordChangeRepository:
    """변경된 비밀번호와 수정 시각을 DB에 저장합니다."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def save_password(self, user: Users, password_hash: str) -> None:
        user.password_hash = password_hash
        user.updated_at = datetime.now(UTC)
        self.db.commit()
