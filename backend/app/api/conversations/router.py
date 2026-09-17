from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.auth.dependencies import get_current_user
from app.core.database import get_db
from app.models.generated import Users
from app.schemas.conversation import ConversationRenameRequest, ConversationResponse
from app.schemas.message import MessageCreateRequest, MessageResponse
from app.services.conversation import ConversationService
from app.services.message import MessageService

router = APIRouter()


@router.get("", response_model=list[ConversationResponse])
def list_conversations(
    current_user: Annotated[Users, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ConversationResponse]:
    return ConversationService(db).list_conversations(current_user.id)


@router.get("/search", response_model=list[ConversationResponse])
def search_conversations(
    current_user: Annotated[Users, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[str, Query(max_length=200)] = "",
) -> list[ConversationResponse]:
    """제목/카테고리(진료과)/대화 내용을 한 번에 검색한다(모드 구분 없음) - 사이드바
    검색창 전용. "/{conversation_id}" 같은 path param 라우트보다 먼저 등록해야
    "search"가 conversation_id로 오인되지 않는다(지금은 그런 라우트가 없어서
    실제로는 안전하지만, 나중에 GET /{conversation_id}가 추가될 걸 대비해
    등록 순서를 먼저 둔다)."""
    return ConversationService(db).search_conversations(current_user.id, q)


@router.post("", response_model=ConversationResponse, status_code=201)
def create_conversation(
    current_user: Annotated[Users, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ConversationResponse:
    return ConversationService(db).create_conversation(current_user.id)


@router.patch("/{conversation_id}", response_model=ConversationResponse)
def rename_conversation(
    conversation_id: str,
    payload: ConversationRenameRequest,
    current_user: Annotated[Users, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ConversationResponse:
    return ConversationService(db).rename_conversation(conversation_id, current_user.id, payload.title)


@router.delete("/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    current_user: Annotated[Users, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    ConversationService(db).delete_conversation(conversation_id, current_user.id)
    return {"status": "ok"}


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
def list_messages(
    conversation_id: str,
    current_user: Annotated[Users, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[MessageResponse]:
    return MessageService(db).list_messages(conversation_id, current_user.id)


@router.post("/{conversation_id}/messages", response_model=MessageResponse, status_code=201)
async def send_message(
    conversation_id: str,
    payload: MessageCreateRequest,
    current_user: Annotated[Users, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MessageResponse:
    return await MessageService(db).send_message(
        conversation_id, current_user, payload.content, payload.attachments, payload.model_id
    )


@router.post("/{conversation_id}/messages/upload", response_model=MessageResponse, status_code=201)
async def send_message_with_uploads(
    conversation_id: str,
    current_user: Annotated[Users, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    files: Annotated[list[UploadFile], File(...)],
    content: Annotated[str, Form(max_length=8_000)] = "",
    model_id: Annotated[str | None, Form(alias="modelId", max_length=100)] = None,
) -> MessageResponse:
    """복수 원본 파일을 검증한 뒤 기존 메시지 저장·응답 생성 흐름을 실행합니다."""

    return await MessageService(db).send_message_with_uploads(
        conversation_id,
        current_user,
        content,
        model_id,
        files,
    )
