"""Cloud Run 본문 크기 제한을 우회하는 관리자 R2 직접 업로드 API입니다.

`/ocr/uploads/*` 4개 엔드포인트는 R2(S3 호환) 멀티파트 업로드 프로토콜의 서로
다른 단계(init 1회 -> part-url 파트마다 반복 -> complete 1회, 실패 시 abort)라
하나로 합칠 수 없다(프론트 frontend/src/features/admin/services/
apiAdminAiService.ts의 실제 호출 순서 참고) - 대신 4곳에서 완전히 똑같던
"LargeUploadValidationError/R2StorageError를 HTTPException으로 바꾸는" 코드는
중복이라, 엔드포인트마다 반복하지 않고 register_upload_error_handlers()로
한 번만 등록한다(2026-09-04)."""

from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.auth.dependencies import require_admin
from app.models.generated import Users
from app.schemas.admin import (
    OcrJobCreatedResponse,
    OcrMultipartPartUrlRequest,
    OcrMultipartPartUrlResponse,
    OcrMultipartUploadAbortRequest,
    OcrMultipartUploadCompleteRequest,
    OcrMultipartUploadCompleteResponse,
    OcrMultipartUploadInitRequest,
    OcrMultipartUploadInitResponse,
    OcrRemoteJobRequest,
)
from app.services.large_upload_service import (
    LargeUploadValidationError,
    large_upload_service,
)
from app.services.ocr_job_service import OcrJobCapacityError, ocr_job_manager
from app.services.r2_storage import R2StorageError

router = APIRouter()
AdminUser = Annotated[Users, Depends(require_admin)]


def register_upload_error_handlers(app: FastAPI) -> None:
    """`create_app()`과 테스트가 둘 다 이 함수로 등록해야 아래 4개 엔드포인트가
    LargeUploadValidationError/R2StorageError를 422/503으로 변환한다 - 이 라우터를
    직접 하위 app에 mount만 하고 이 함수를 안 부르면(예: 예전 테스트처럼) 두
    예외가 처리되지 않은 500으로 나간다."""

    @app.exception_handler(LargeUploadValidationError)
    async def _handle_validation_error(_request: Request, exc: LargeUploadValidationError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content={"detail": str(exc)})

    @app.exception_handler(R2StorageError)
    async def _handle_storage_error(_request: Request, exc: R2StorageError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"detail": str(exc)})


@router.post("/ocr/uploads/init", response_model=OcrMultipartUploadInitResponse)
def initiate_upload(
    payload: OcrMultipartUploadInitRequest,
    _admin: AdminUser,
) -> OcrMultipartUploadInitResponse:
    return OcrMultipartUploadInitResponse.model_validate(
        large_upload_service.initiate(
            payload.file_name,
            payload.file_size,
            payload.content_type,
        )
    )


@router.post("/ocr/uploads/part-url", response_model=OcrMultipartPartUrlResponse)
def create_part_url(
    payload: OcrMultipartPartUrlRequest,
    _admin: AdminUser,
) -> OcrMultipartPartUrlResponse:
    url = large_upload_service.create_part_url(
        payload.object_key,
        payload.upload_id,
        payload.part_number,
    )
    return OcrMultipartPartUrlResponse(uploadUrl=url)


@router.post("/ocr/uploads/complete", response_model=OcrMultipartUploadCompleteResponse)
def complete_upload(
    payload: OcrMultipartUploadCompleteRequest,
    _admin: AdminUser,
) -> OcrMultipartUploadCompleteResponse:
    return OcrMultipartUploadCompleteResponse.model_validate(
        large_upload_service.complete(
            object_key=payload.object_key,
            upload_id=payload.upload_id,
            file_size=payload.file_size,
            parts=payload.parts,
        )
    )


@router.post("/ocr/uploads/abort", status_code=status.HTTP_204_NO_CONTENT)
def abort_upload(payload: OcrMultipartUploadAbortRequest, _admin: AdminUser) -> Response:
    large_upload_service.abort(payload.object_key, payload.upload_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/ocr/jobs/remote",
    response_model=OcrJobCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_remote_ocr_job(
    payload: OcrRemoteJobRequest,
    _admin: AdminUser,
) -> OcrJobCreatedResponse:
    try:
        return await ocr_job_manager.create_remote_job(
            object_key=payload.object_key,
            file_name=payload.file_name,
            file_size=payload.file_size,
            content_type=payload.content_type,
            chunk_size=payload.chunk_size,
            overlap=payload.overlap,
        )
    except OcrJobCapacityError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from exc
