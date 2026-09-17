from datetime import datetime

from pydantic import BaseModel, Field


class MessageAttachmentInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    size: int | None = None
    type: str | None = None


class MessageAttachmentResponse(BaseModel):
    id: str
    file_name: str
    file_type: str | None
    file_size_bytes: int | None


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime
    attachments: list[MessageAttachmentResponse] = []


class MessageCreateRequest(BaseModel):
    # 첨부파일만 보내고 텍스트는 없는 경우가 있어(프론트 MessageInput 참고) content는
    # 비어있을 수 있다 — "텍스트도 첨부도 둘 다 없음"만 서비스 계층에서 막는다.
    content: str = Field(default="", max_length=8000)
    attachments: list[MessageAttachmentInput] = []
    # Frontend ModelSelect의 ID는 Vast.ai 원격 Model Registry의 ID와 일치해야 한다.
    # 생략하면 ai.consultation.pipeline.DEFAULT_MODEL_ID를 사용한다.
    model_id: str | None = None
