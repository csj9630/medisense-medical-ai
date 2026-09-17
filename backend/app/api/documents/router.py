from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from app.api.auth.dependencies import get_current_user
from app.core.logging import get_logger
from app.models.generated import Users
from app.schemas.document import OcrLineResponse, OcrResponse
from app.services.ocr_workflow import analyze_uploaded_document
from ai.ocr.errors import (
    DocumentProcessingError,
    DocumentTooLargeError,
    DocumentValidationError,
    OcrUnavailableError,
)

router = APIRouter()
logger = get_logger("api.documents")

# 파일 크기·페이지 수 등 검증 기준은 core/config.py의 ocr_* 설정을 따릅니다.


@router.post("/ocr", response_model=OcrResponse)
async def extract_text(
    file: UploadFile,
    current_user: Annotated[Users, Depends(get_current_user)],
) -> OcrResponse:
    """업로드한 문서/ZIP에서 텍스트를 추출한다 (채팅 첨부파일 미리보기 패널에서 호출).

    파일을 저장하지는 않는다 — OCR 결과만 즉시 반환하고 끝. 원본을 서버에 남겨야
    하면 Object Storage(R2) 연동 후 여기서 업로드까지 같이 처리하면 된다.
    """
    try:
        result = await analyze_uploaded_document(file)
    except DocumentTooLargeError as exc:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(exc)) from exc
    except DocumentValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except OcrUnavailableError as exc:
        logger.exception("OCR 엔진을 사용할 수 없습니다.")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except DocumentProcessingError as exc:
        logger.exception("OCR 처리 실패")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "텍스트 추출에 실패했습니다.") from exc

    # 공통 Core가 보존한 실제 OCR Line만 기존 채팅 Response에 맞게 변환합니다.
    lines = [
        OcrLineResponse(
            text=line.text,
            confidence=line.confidence,
            page=line.page,
        )
        for line in result.lines
    ]
    return OcrResponse(text=result.cleaned_text, lines=lines)
