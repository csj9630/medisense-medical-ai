"""채팅 multipart 첨부파일의 수, 형식과 크기를 검증합니다."""

from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.schemas.message import MessageAttachmentInput

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".docx",
    ".pptx",
    ".txt",
    ".csv",
}
SUPPORTED_LABEL = "PDF, PNG, JPG, DOCX, PPTX, TXT, CSV"


async def validate_message_uploads(
    files: list[UploadFile],
) -> list[MessageAttachmentInput]:
    """복수 파일을 한 번씩 제한 크기까지만 읽고 안전한 메타데이터를 반환합니다."""

    if not files:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "첨부할 파일을 선택해 주세요.")
    if len(files) > settings.message_max_files_per_request:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"한 메시지에는 최대 {settings.message_max_files_per_request}개까지 첨부할 수 있습니다.",
        )

    max_file_bytes = settings.message_max_file_size_mb * 1024 * 1024
    attachments: list[MessageAttachmentInput] = []

    for file in files:
        # 브라우저가 전달한 경로 조각은 제거하고 DB 길이 제한 안의 원본 이름만 사용합니다.
        file_name = Path((file.filename or "").replace("\\", "/")).name
        extension = Path(file_name).suffix.lower()
        if not file_name or len(file_name) > 255:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "파일명은 1자 이상 255자 이하여야 합니다.",
            )
        if extension not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"{SUPPORTED_LABEL} 파일만 첨부할 수 있습니다.",
            )

        content = await file.read(max_file_bytes + 1)
        if not content:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{file_name}: 빈 파일입니다.")
        if len(content) > max_file_bytes:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                f"{file_name}: 파일 크기는 {settings.message_max_file_size_mb}MB 이하여야 합니다.",
            )

        attachments.append(
            MessageAttachmentInput(
                name=file_name,
                size=len(content),
                type=(file.content_type or "application/octet-stream")[:50],
            )
        )

    return attachments
