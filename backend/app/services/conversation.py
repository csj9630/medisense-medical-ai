from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.generated import Conversations
from app.repositories.conversation import ConversationRepository
from app.schemas.conversation import ConversationResponse


def to_conversation_response(conversation: Conversations) -> ConversationResponse:
    return ConversationResponse(
        id=str(conversation.id),
        title=conversation.title,
        is_title_custom=bool(conversation.is_title_custom),
        category=conversation.category,
        updated_at=conversation.updated_at,
    )


class ConversationService:
    def __init__(self, db: Session) -> None:
        self.repository = ConversationRepository(db)

    def list_conversations(self, user_id: UUID) -> list[ConversationResponse]:
        conversations = self.repository.list_by_user(user_id)
        return [to_conversation_response(c) for c in conversations]

    def search_conversations(self, user_id: UUID, query: str) -> list[ConversationResponse]:
        # 빈 검색어면 "전부 다 매칭"으로 보지 않고 전체 목록을 그대로 보여준다
        # (ILIKE '%%'도 결과상 같지만, 의도를 명확히 하고 불필요한 join 스캔을 피함).
        stripped = query.strip()
        if not stripped:
            return self.list_conversations(user_id)
        conversations = self.repository.search(user_id, stripped)
        return [to_conversation_response(c) for c in conversations]

    def create_conversation(self, user_id: UUID) -> ConversationResponse:
        conversation = self.repository.create(user_id)
        return to_conversation_response(conversation)

    def rename_conversation(self, conversation_id: str, user_id: UUID, title: str) -> ConversationResponse:
        conversation = self.get_owned(conversation_id, user_id)
        conversation = self.repository.rename(conversation, title)
        return to_conversation_response(conversation)

    def delete_conversation(self, conversation_id: str, user_id: UUID) -> None:
        conversation = self.get_owned(conversation_id, user_id)
        self.repository.delete(conversation)

    def get_owned(self, conversation_id: str, user_id: UUID) -> Conversations:
        """대화를 찾고, 이 유저 소유가 아니면(또는 없으면) 404로 통일해 존재 여부를 숨긴다."""
        try:
            conversation = self.repository.find_by_id(UUID(conversation_id))
        except ValueError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "대화를 찾을 수 없습니다.") from error
        if not conversation or conversation.user_id != user_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "대화를 찾을 수 없습니다.")
        return conversation
