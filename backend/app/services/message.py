import asyncio
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ai.consultation import ConsultationResult, consult, get_default_classifier
from ai.consultation.history import select_history
from ai.llm.contracts import LlmMessage
from ai.rag import RetrievedChunk
from app.core.config import settings
from app.core.logging import get_logger
from app.models.generated import Conversations, Messages, Users
from app.repositories.consultation_log import ConsultationLogRepository
from app.repositories.conversation import ConversationRepository
from app.repositories.message import MessageRepository
from app.schemas.message import MessageAttachmentInput, MessageAttachmentResponse, MessageResponse
from app.services import rag_search_service
from app.services.conversation import ConversationService
from app.services.llm_runtime import llm_application
from app.services.message_upload import validate_message_uploads

logger = get_logger("services.message")

# 채팅·일반 LLM API·Admin 비교 API가 공통 Runtime을 공유한다.


def to_message_response(message: Messages) -> MessageResponse:
    return MessageResponse(
        id=str(message.id),
        role=message.role,
        content=message.content,
        created_at=message.created_at,
        attachments=[
            MessageAttachmentResponse(
                id=str(a.id),
                file_name=a.file_name,
                file_type=a.file_type,
                file_size_bytes=a.file_size_bytes,
            )
            for a in message.message_attachments
        ],
    )


class MessageService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.conversations_service = ConversationService(db)
        self.conversations = ConversationRepository(db)
        self.messages = MessageRepository(db)
        self.consultation_logs = ConsultationLogRepository(db)

    def list_messages(self, conversation_id: str, user_id: UUID) -> list[MessageResponse]:
        conversation = self.conversations_service.get_owned(conversation_id, user_id)
        messages = self.messages.list_by_conversation(conversation.id)
        return [to_message_response(m) for m in messages]

    async def send_message_with_uploads(
        self,
        conversation_id: str,
        current_user: Users,
        content: str,
        model_id: str | None,
        files: list[UploadFile],
    ) -> MessageResponse:
        """업로드 원본을 검증하고 안전한 메타데이터만 기존 메시지 흐름에 전달합니다."""

        attachments = await validate_message_uploads(files)
        return await self.send_message(
            conversation_id,
            current_user,
            content,
            attachments,
            model_id,
        )

    async def send_message(
        self,
        conversation_id: str,
        current_user: Users,
        content: str,
        attachments: list[MessageAttachmentInput] | None = None,
        model_id: str | None = None,
    ) -> MessageResponse:
        attachments = attachments or []
        content = content.strip()
        if not content and not attachments:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "메시지 내용이나 첨부파일이 필요합니다.")

        conversation = self.conversations_service.get_owned(conversation_id, current_user.id)
        self._check_guest_limits(current_user, new_attachment_count=len(attachments))

        previous_messages = self.messages.list_by_conversation(conversation.id)
        is_first_message = not previous_messages
        # 현재 질문을 저장하기 전에 스냅샷을 만들어 중복 전달을 막는다.
        history = select_history(tuple(
            LlmMessage(role=message.role, content=message.content)
            for message in previous_messages
        ))

        user_message = self.messages.create(conversation.id, "user", content)
        if attachments:
            self.messages.create_attachments(
                user_message.id, [a.model_dump() for a in attachments]
            )

        if is_first_message and not conversation.is_title_custom:
            self.conversations.set_auto_title(conversation, content or attachments[0].name)

        reply_content, result = await self._generate_reply(
            content, conversation, model_id, history=history
        )

        assistant_message = self.messages.create(conversation.id, "assistant", reply_content)
        self.conversations.touch(conversation)

        # 첨부파일만 온 경우(result가 None)는 실제 상담이 아니라서 로그를 안 남긴다.
        if result is not None:
            self._log_consultation(current_user.id, conversation.id, assistant_message.id, result)

        return to_message_response(assistant_message)

    async def _generate_reply(
        self, content: str, conversation: Conversations, model_id: str | None = None,
        *, history: tuple[LlmMessage, ...] = (),
    ) -> tuple[str, ConsultationResult | None]:
        # 텍스트가 없고 첨부파일만 있는 경우(OCR 미연동 상태라 첨부 내용을 알 수 없음)엔
        # LLM 호출 자체가 의미 없어서 안내 문구만 반환한다 — 실제 상담이 아니므로
        # 대시보드 로그도 안 남긴다(호출부가 result=None으로 판단).
        if not content:
            return (
                "첨부해주신 파일은 확인했어요. 증상이나 궁금하신 점을 글로도 함께 적어주시면 더 정확히 답변드릴 수 있어요.",
                None,
            )

        # RAG 검색 부스트와 상담 프롬프트에 같은 진료과 분류 결과를 전달한다.
        classifier = get_default_classifier()
        department_result = classifier.classify(content)
        search_query = content
        # "어제부터요"처럼 단독 분류가 안 되는 후속 답변은 최근 사용자 발언을
        # 함께 검색한다. AI의 추측을 사용자 증상으로 분류하지 않는다.
        if department_result.department is None and history:
            recent_questions = [m.content for m in history if m.role == "user"][-3:]
            context_questions: list[str] = []
            for question in reversed(recent_questions):
                context_questions.append(question)
                previous_department = classifier.classify(question)
                if previous_department.department is not None:
                    # 주제가 바뀐 뒤에는 더 오래된 진료과의 키워드를 섞지 않는다.
                    department_result = previous_department
                    break
            if context_questions:
                search_query = "\n".join([*reversed(context_questions), content])
        reference_chunks = await asyncio.to_thread(
            self._search_reference_chunks, search_query, department_result.department
        )

        consult_kwargs = {"model_id": model_id} if model_id else {}
        result: ConsultationResult = await consult(
            llm_application,
            content,
            history=history,
            reference_chunks=reference_chunks,
            department_result=department_result,
            **consult_kwargs,
        )

        # LLM 호출 자체가 실패한 경우(is_fallback)는 실제 상담이 이뤄진 게 아니므로
        # 카테고리를 아예 건드리지 않는다 — 여기서 "기타"로 확정해버리면, 다음에
        # 같은 대화에서 정상 응답이 나와도 "이미 값이 있음" 취급돼(set_category_if_unset)
        # 영영 "기타"로 잘못 고정된다.
        if not result.is_fallback:
            # 분류기가 진료과를 특정하지 못해도(department=None) 카테고리를 비워두지
            # 않고 "기타"로 채운다 — 사이드바 "진료과별" 그룹에서 미분류로 안 남게 한다.
            self.conversations.set_category_if_unset(conversation, result.department or "기타")

        return result.answer, result

    def _log_consultation(
        self, user_id: UUID, conversation_id: UUID, message_id: UUID, result: ConsultationResult
    ) -> None:
        """관리자 대시보드용 로그를 남긴다. 로깅 자체가 실패해도(DB 오류 등) 채팅
        응답은 이미 사용자에게 나갈 값이 정해진 뒤라 — RAG 검색 실패 때와 같은
        이유로 절대 요청을 죽이지 않는다. 실패하면 조용히 로깅만 건너뛴다."""
        try:
            self.consultation_logs.create(
                user_id=user_id, conversation_id=conversation_id, message_id=message_id, result=result
            )
        except Exception:
            logger.exception("consultation_logs 저장 실패 — 응답 자체는 정상 처리됨: message_id=%s", message_id)
            self.db.rollback()

    def _search_reference_chunks(
        self, query: str, department: str | None = None
    ) -> list[RetrievedChunk]:
        """RAG 검색 결과를 consult()의 참고 의료 정보로 넘긴다. RAG 데이터셋이 아직
        Neon에 안 들어갔거나(테이블은 있는데 0건) 마이그레이션 자체가 아직 안
        적용된 경우(테이블 없음) 등 어떤 이유로든 검색이 실패해도, 여기서 잡아서
        빈 결과를 반환한다 — consult()는 빈/None 결과를 "참고 정보 없음" 경로로
        처리하므로 채팅은 LLM+프롬프트 엔지니어링만으로 계속 응답한다(안 죽음).
        나중에 실제 데이터가 채워지면 이 함수는 코드 변경 없이 그대로 검색 결과를
        반환하기 시작한다.

        `department`: 호출부(_generate_reply)가 미리 분류해서 넘긴 진료과 -
        rag_search_service.search()의 진료과 소프트 부스트에 쓰인다."""
        try:
            return rag_search_service.search(self.db, query, department=department)
        except Exception:
            logger.exception("RAG 검색 실패 — 참고 정보 없이 LLM/프롬프트만으로 응답을 이어감: query=%r", query)
            # DB 오류(예: 마이그레이션 전이라 chunk_embeddings 테이블이 아직 없음)는
            # Postgres 트랜잭션 자체를 abort 상태로 만든다 — rollback을 안 하면 이후
            # 이 요청에서 하는 모든 DB 작업(응답 메시지 저장 등)이 함께 실패한다.
            self.db.rollback()
            return []

    def _check_guest_limits(self, current_user: Users, new_attachment_count: int) -> None:
        if current_user.auth_provider != "guest":
            return

        sent = self.messages.count_user_messages_total(current_user.id)
        if sent >= settings.guest_message_limit:
            logger.info("게스트 메시지 한도 초과: user_id=%s sent=%s", current_user.id, sent)
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"게스트는 최대 {settings.guest_message_limit}개의 메시지를 보낼 수 있어요. "
                "로그인하면 이어서 이용할 수 있어요.",
            )

        if new_attachment_count:
            attached = self.messages.count_user_attachments_total(current_user.id)
            if attached + new_attachment_count > settings.guest_attachment_limit:
                logger.info("게스트 첨부파일 한도 초과: user_id=%s attached=%s", current_user.id, attached)
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    f"게스트는 최대 {settings.guest_attachment_limit}개의 파일을 첨부할 수 있어요. "
                    "로그인하면 이어서 이용할 수 있어요.",
                )
