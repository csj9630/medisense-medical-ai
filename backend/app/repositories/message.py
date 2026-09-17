from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.generated import Conversations, MessageAttachments, Messages


class MessageRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_by_conversation(self, conversation_id: UUID) -> list[Messages]:
        stmt = (
            select(Messages)
            .where(Messages.conversation_id == conversation_id)
            .order_by(Messages.created_at.asc())
        )
        return list(self.db.scalars(stmt))

    def create(self, conversation_id: UUID, role: str, content: str) -> Messages:
        message = Messages(conversation_id=conversation_id, role=role, content=content)
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message

    def create_attachments(
        self, message_id: UUID, attachments: list[dict]
    ) -> list[MessageAttachments]:
        """첨부파일 '메타데이터'만 기록한다 (실제 파일 저장은 아직 없음).

        Object Storage(R2 등) 연동 전까지 file_url은 실제로 열람 불가능한
        placeholder다 — 나중에 스토리지가 붙으면 진짜 업로드 URL로 채워 넣으면 된다.
        """
        rows = [
            MessageAttachments(
                message_id=message_id,
                file_url=f"pending-upload://{message_id}/{a['name']}",
                file_name=a["name"],
                file_type=a.get("type"),
                file_size_bytes=a.get("size"),
            )
            for a in attachments
        ]
        self.db.add_all(rows)
        self.db.commit()
        return rows

    def count_user_messages_total(self, user_id: UUID) -> int:
        """게스트 총 메시지 한도 체크용 — 이 유저가 지금까지 보낸 user 메시지 수."""
        stmt = (
            select(func.count(Messages.id))
            .join(Conversations, Messages.conversation_id == Conversations.id)
            .where(Conversations.user_id == user_id, Messages.role == "user")
        )
        return self.db.scalar(stmt) or 0

    def count_user_attachments_total(self, user_id: UUID) -> int:
        """게스트 총 첨부파일 한도 체크용."""
        stmt = (
            select(func.count(MessageAttachments.id))
            .join(Messages, MessageAttachments.message_id == Messages.id)
            .join(Conversations, Messages.conversation_id == Conversations.id)
            .where(Conversations.user_id == user_id)
        )
        return self.db.scalar(stmt) or 0
