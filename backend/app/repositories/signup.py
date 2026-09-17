from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.generated import EmailVerifications, Users


class SignupRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def find_user_by_email(self, email: str) -> Users | None:
        return self.db.scalar(select(Users).where(Users.email == email))

    def create_user(self, email: str, password_hash: str) -> Users:
        user = Users(email=email, password_hash=password_hash, is_email_verified=False)
        self.db.add(user)
        self.db.flush()
        return user

    def replace_verification_code(self, email: str, code: str, expires_at: datetime) -> None:
        self.db.execute(delete(EmailVerifications).where(EmailVerifications.email == email))
        self.db.add(EmailVerifications(email=email, code=code, expires_at=expires_at))

    def find_verification(self, email: str, code: str) -> EmailVerifications | None:
        return self.db.scalar(select(EmailVerifications).where(
            EmailVerifications.email == email, EmailVerifications.code == code
        ))

    def commit(self) -> None:
        self.db.commit()
