from typing import Literal

from pydantic import BaseModel, Field


class LlmModelResponse(BaseModel):
    model_id: str
    label: str
    description: str


class LlmMessageInput(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class LlmGenerateRequest(BaseModel):
    model_id: str
    messages: list[LlmMessageInput] = Field(min_length=1)


class LlmGenerateResponse(BaseModel):
    model_id: str
    content: str


class LlmCompareRequest(BaseModel):
    model_ids: list[str] = Field(min_length=1)
    messages: list[LlmMessageInput] = Field(min_length=1)


class LlmCompareResult(BaseModel):
    model_id: str
    content: str | None = None
    error: str | None = None
