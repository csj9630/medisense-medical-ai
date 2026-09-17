"""8GiB 관리자 RAG 파일을 R2 멀티파트로 안전하게 전송하는 계약입니다."""

import math
import re
from pathlib import Path
from uuid import uuid4

from app.core.config import Settings, settings
from app.schemas.admin import OcrMultipartCompletedPart
from app.services.r2_storage import R2StorageService, rag_r2_storage

MIB = 1024**2
# R2(S3 호환) 멀티파트는 Part 개수가 최대 10,000개다. 8GiB(config.py의
# ocr_max_file_size_mb) 파일을 64MiB Part로 나누면 최대 128개라 한도에 여유가
# 크다 - Part를 더 작게 잡으면(예: 5MiB, S3 최소 크기) 8GiB 기준 1,600여 개까지
# 늘어나 HTTP 요청 수가 늘고, 더 크게 잡으면 Part 하나 재시도 실패 시 다시
# 올려야 하는 용량이 커진다. 64MiB는 그 사이의 절충값이다.
UPLOAD_PART_SIZE_BYTES = 64 * MIB
UPLOAD_PREFIX = "admin-rag-uploads/"
SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".docx",
    ".pptx",
    ".json",
    ".jsonl",
    ".csv",
    ".txt",
    ".zip",
}
SAFE_FILE_NAME = re.compile(r"[^0-9A-Za-z가-힣._-]+")


class LargeUploadValidationError(Exception):
    """대용량 업로드 요청이 크기·파일명·Part 계약을 만족하지 않습니다."""


class LargeUploadService:
    def __init__(
        self,
        storage: R2StorageService = rag_r2_storage,
        app_settings: Settings = settings,
    ) -> None:
        self.storage = storage
        self.max_file_bytes = app_settings.ocr_max_file_size_mb * MIB

    def initiate(self, file_name: str, file_size: int, content_type: str) -> dict:
        safe_name = self._validate_file(file_name, file_size)
        object_key = f"{UPLOAD_PREFIX}{uuid4().hex}/{safe_name}"
        upload_id = self.storage.create_multipart_upload(
            key=object_key,
            content_type=content_type,
            file_name=safe_name,
            file_size=file_size,
        )
        return {
            "uploadId": upload_id,
            "objectKey": object_key,
            "partSize": UPLOAD_PART_SIZE_BYTES,
            "partCount": math.ceil(file_size / UPLOAD_PART_SIZE_BYTES),
        }

    def create_part_url(self, object_key: str, upload_id: str, part_number: int) -> str:
        self._validate_object_key(object_key)
        if not 1 <= part_number <= 10_000:
            raise LargeUploadValidationError("올바르지 않은 업로드 Part 번호입니다.")
        return self.storage.presign_upload_part(
            key=object_key,
            upload_id=upload_id,
            part_number=part_number,
        )

    def complete(
        self,
        *,
        object_key: str,
        upload_id: str,
        file_size: int,
        parts: list[OcrMultipartCompletedPart],
    ) -> dict:
        self._validate_object_key(object_key)
        if not 0 < file_size <= self.max_file_bytes:
            raise LargeUploadValidationError("파일은 8GB 이하만 업로드할 수 있습니다.")

        expected_count = math.ceil(file_size / UPLOAD_PART_SIZE_BYTES)
        ordered = sorted(parts, key=lambda part: part.part_number)
        if [part.part_number for part in ordered] != list(range(1, expected_count + 1)):
            raise LargeUploadValidationError("업로드 Part가 누락되었거나 중복되었습니다.")

        etag = self.storage.complete_multipart_upload(
            key=object_key,
            upload_id=upload_id,
            parts=[
                {"PartNumber": part.part_number, "ETag": part.etag}
                for part in ordered
            ],
        )
        metadata = self.storage.head_object(object_key)
        actual_size = int(metadata.get("ContentLength", -1))
        if actual_size != file_size:
            self.storage.delete_object(object_key)
            raise LargeUploadValidationError(
                f"업로드 크기가 일치하지 않습니다. 예상 {file_size}B, 실제 {actual_size}B"
            )
        return {"objectKey": object_key, "etag": etag, "fileSize": actual_size}

    def abort(self, object_key: str, upload_id: str) -> None:
        self._validate_object_key(object_key)
        self.storage.abort_multipart_upload(key=object_key, upload_id=upload_id)

    def _validate_file(self, file_name: str, file_size: int) -> str:
        normalized_name = Path(file_name.replace("\\", "/")).name
        extension = Path(normalized_name).suffix.lower()
        if not normalized_name or extension not in SUPPORTED_EXTENSIONS:
            raise LargeUploadValidationError("지원하지 않는 파일 형식입니다.")
        if not 0 < file_size <= self.max_file_bytes:
            raise LargeUploadValidationError("파일은 8GB 이하만 업로드할 수 있습니다.")
        stem = SAFE_FILE_NAME.sub("_", Path(normalized_name).stem).strip("._") or "document"
        return f"{stem[:200]}{extension}"

    @staticmethod
    def _validate_object_key(object_key: str) -> None:
        # object_key는 클라이언트가 이후 요청(part-url/complete/abort)마다 그대로
        # 돌려보내는 값이라, 검증 없이 그대로 R2 호출에 쓰면 그 값을 조작해서
        # UPLOAD_PREFIX 밖의 임의 경로에 접근/덮어쓰기(path traversal)할 수 있다 -
        # 반드시 우리가 발급한 접두어로 시작하고 ".." 세그먼트가 없는지 확인한다.
        if not object_key.startswith(UPLOAD_PREFIX) or ".." in object_key.split("/"):
            raise LargeUploadValidationError("올바르지 않은 R2 Object Key입니다.")


large_upload_service = LargeUploadService()
