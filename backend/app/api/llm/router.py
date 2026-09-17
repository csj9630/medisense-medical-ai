from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.auth.dependencies import get_current_user, require_admin
from app.models.generated import Users
from app.schemas.llm import (
    LlmCompareRequest,
    LlmCompareResult,
    LlmGenerateRequest,
    LlmGenerateResponse,
    LlmModelResponse,
)
from app.services.llm_service import compare, generate, list_available_models

router = APIRouter()


@router.get("/models", response_model=list[LlmModelResponse])
def get_models() -> list[LlmModelResponse]:
    """Vast.ai에 연결된 5개 모델 목록을 가벼운 Registry 조회로 반환합니다."""
    return list_available_models()


@router.post("/generate", response_model=LlmGenerateResponse)
async def generate_response(
    payload: LlmGenerateRequest,
    current_user: Annotated[Users, Depends(get_current_user)],
) -> LlmGenerateResponse:
    """선택한 Vast.ai 원격 모델로 응답을 생성합니다."""
    return await generate(payload.model_id, payload.messages)


@router.post("/compare", response_model=list[LlmCompareResult])
async def compare_models(
    payload: LlmCompareRequest,
    current_user: Annotated[Users, Depends(require_admin)],
) -> list[LlmCompareResult]:
    """여러 모델에 같은 프롬프트를 넣어 비교 — 관리자 페이지 LLM 탭용, 관리자 전용."""
    return await compare(payload.model_ids, payload.messages)
