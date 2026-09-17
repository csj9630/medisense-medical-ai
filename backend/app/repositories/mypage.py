from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models.generated import AdminDocuments, Conversations, EmailVerifications, Users


class MyPageRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def usage_summary(self, user: Users) -> tuple[int, object | None]:
        row = self.db.execute(
            select(func.count(Conversations.id), func.max(Conversations.created_at)).where(
                Conversations.user_id == user.id
            )
        ).one()
        return int(row[0]), row[1]

    def delete_account(self, user: Users) -> None:
        # 업로드 문서는 유지하되 탈퇴 사용자와의 연결만 해제합니다.
        self.db.execute(
            update(AdminDocuments).where(AdminDocuments.uploaded_by == user.id).values(uploaded_by=None)
        )
        self.db.execute(delete(EmailVerifications).where(EmailVerifications.email == user.email))
        self.db.delete(user)
        self.db.commit()

    def delete_all_consultations(self, user: Users) -> int:
        # conversations의 FK에 ON DELETE CASCADE가 설정되어 메시지와 첨부도 함께 삭제됩니다.
        result = self.db.execute(delete(Conversations).where(Conversations.user_id == user.id))
        self.db.commit()
        return int(result.rowcount or 0)
