from datetime import datetime

from pydantic import BaseModel, Field


class ConversationResponse(BaseModel):
    id: str
    title: str | None
    is_title_custom: bool
    category: str | None
    updated_at: datetime


class ConversationRenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
