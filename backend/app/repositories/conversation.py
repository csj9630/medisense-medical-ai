from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.models.generated import Conversations, Messages


class ConversationRepository:
    """대화(conversation) 목록 조회/생성/수정만 담당합니다. 소유권 검사는 서비스 계층에서."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_by_user(self, user_id: UUID) -> list[Conversations]:
        stmt = (
            select(Conversations)
            .where(Conversations.user_id == user_id)
            .order_by(Conversations.updated_at.desc())
        )
        return list(self.db.scalars(stmt))

    def search(self, user_id: UUID, query: str) -> list[Conversations]:
        """제목/카테고리(진료과)/대화 내용 중 하나라도 일치하면 결과에 포함한다 -
        검색 종류를 사용자가 고르게 하지 않고 한 번에 다 확인한다(요청 사항).
        메시지 내용 매칭 때문에 join이 필요해서 같은 대화가 메시지 여러 개에서
        중복 매칭될 수 있어 distinct()로 한 번만 나오게 한다."""
        like_pattern = f"%{query}%"
        stmt = (
            select(Conversations)
            .distinct()
            .outerjoin(Messages, Messages.conversation_id == Conversations.id)
            .where(
                Conversations.user_id == user_id,
                or_(
                    Conversations.title.ilike(like_pattern),
                    Conversations.category.ilike(like_pattern),
                    Messages.content.ilike(like_pattern),
                ),
            )
            .order_by(Conversations.updated_at.desc())
        )
        return list(self.db.scalars(stmt))

    def create(self, user_id: UUID) -> Conversations:
        conversation = Conversations(user_id=user_id, title="새 대화", is_title_custom=False)
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def find_by_id(self, conversation_id: UUID) -> Conversations | None:
        return self.db.get(Conversations, conversation_id)

    def rename(self, conversation: Conversations, title: str) -> Conversations:
        conversation.title = title
        conversation.is_title_custom = True
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def delete(self, conversation: Conversations) -> None:
        # ORM의 session.delete()는 자식 messages를 지우는 대신 conversation_id를
        # NULL로 바꾸려다 NOT NULL 제약에 걸린다 (messages 관계에 cascade 설정이 없음).
        # DB의 FK가 이미 ON DELETE CASCADE라서, raw DELETE로 그 카스케이드에 맡긴다.
        self.db.execute(delete(Conversations).where(Conversations.id == conversation.id))
        self.db.commit()

    def touch(self, conversation: Conversations) -> None:
        # updated_at에 DB 트리거가 없으므로(생성 시 server_default만 있음) 여기서 직접 갱신한다.
        conversation.updated_at = datetime.now(UTC)
        self.db.commit()

    def set_auto_title(self, conversation: Conversations, content: str) -> None:
        """첫 메시지로 제목을 자동으로 채운다. 사용자가 직접 이름을 바꾼 적 있으면
        건드리지 않는다 (is_title_custom는 유지 — 이건 '자동' 제목이라서)."""
        title = content.strip().replace("\n", " ")
        if len(title) > 40:
            title = title[:40].rstrip() + "…"
        if not title:
            return
        conversation.title = title
        self.db.commit()

    def reassign_owner(self, *, from_user_id: UUID, to_user_id: UUID) -> int:
        """게스트로 대화하다 로그인한 경우, 게스트 계정 명의의 대화를 실제 계정으로
        옮긴다. 대화 자체(제목/카테고리/메시지)는 그대로 두고 소유자만 바꾼다."""
        result = self.db.execute(
            update(Conversations)
            .where(Conversations.user_id == from_user_id)
            .values(user_id=to_user_id)
        )
        self.db.commit()
        return result.rowcount or 0

    def set_category_if_unset(self, conversation: Conversations, category: str) -> None:
        """진료과 분류 결과로 카테고리를 채운다. 이미 값이 있으면(사용자가 나중에 직접
        바꿀 수 있게 될 걸 대비) 덮어쓰지 않는다 — 대화 도중 증상이 바뀌어 분류 결과가
        흔들려도 사이드바의 '진료과별' 그룹이 계속 바뀌지 않게 하기 위함."""
        if conversation.category:
            return
        conversation.category = category
        self.db.commit()
