from collections.abc import Iterator
from io import BytesIO
from typing import BinaryIO
from urllib.parse import quote

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.storage_config import storage_settings


class R2StorageError(Exception):
    """R2 API 호출이 실패했을 때 상위 업로드/처리 계층에 노출하는 예외입니다."""


class R2StorageService:
    """Cloudflare R2의 S3 호환 API를 통해 파일을 저장합니다."""

    def __init__(self, bucket_name: str | None = None) -> None:
        self.bucket_name = bucket_name or storage_settings.r2_bucket_name

    def _client(self):
        storage_settings.validate_r2_credentials()
        return boto3.client(
            service_name="s3",
            endpoint_url=f"https://{storage_settings.r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=storage_settings.r2_access_key_id,
            aws_secret_access_key=storage_settings.r2_secret_access_key,
            region_name="auto",
        )

    def upload(self, content: bytes, key: str, content_type: str) -> str:
        storage_settings.validate_r2()
        self._client().upload_fileobj(
            BytesIO(content),
            self.bucket_name,
            key,
            ExtraArgs={"ContentType": content_type, "CacheControl": "public, max-age=31536000"},
        )
        return f"{storage_settings.r2_public_url.rstrip('/')}/{key}"

    def create_multipart_upload(
        self,
        *,
        key: str,
        content_type: str,
        file_name: str,
        file_size: int,
    ) -> str:
        try:
            response = self._client().create_multipart_upload(
                Bucket=self.bucket_name,
                Key=key,
                ContentType=content_type,
                Metadata={
                    "original-file-name": quote(file_name, safe="._-"),
                    "declared-file-size": str(file_size),
                },
            )
            return str(response["UploadId"])
        except (BotoCoreError, ClientError, KeyError) as exc:
            raise R2StorageError("R2 멀티파트 업로드를 시작하지 못했습니다.") from exc

    def presign_upload_part(
        self,
        *,
        key: str,
        upload_id: str,
        part_number: int,
        expires_seconds: int = 3_600,
    ) -> str:
        try:
            return self._client().generate_presigned_url(
                "upload_part",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": key,
                    "UploadId": upload_id,
                    "PartNumber": part_number,
                },
                ExpiresIn=expires_seconds,
            )
        except (BotoCoreError, ClientError) as exc:
            raise R2StorageError("업로드 Part URL을 생성하지 못했습니다.") from exc

    def complete_multipart_upload(
        self,
        *,
        key: str,
        upload_id: str,
        parts: list[dict[str, int | str]],
    ) -> str:
        try:
            response = self._client().complete_multipart_upload(
                Bucket=self.bucket_name,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )
            return str(response.get("ETag", "")).strip('"')
        except (BotoCoreError, ClientError) as exc:
            raise R2StorageError("R2 멀티파트 업로드를 완료하지 못했습니다.") from exc

    def upload_part(
        self,
        *,
        key: str,
        upload_id: str,
        part_number: int,
        content: bytes,
    ) -> str:
        try:
            response = self._client().upload_part(
                Bucket=self.bucket_name,
                Key=key,
                UploadId=upload_id,
                PartNumber=part_number,
                Body=content,
            )
            return str(response["ETag"])
        except (BotoCoreError, ClientError, KeyError) as exc:
            raise R2StorageError("R2 임시 결과 Part를 저장하지 못했습니다.") from exc

    def abort_multipart_upload(self, *, key: str, upload_id: str) -> None:
        try:
            self._client().abort_multipart_upload(
                Bucket=self.bucket_name,
                Key=key,
                UploadId=upload_id,
            )
        except (BotoCoreError, ClientError) as exc:
            raise R2StorageError("R2 멀티파트 업로드를 취소하지 못했습니다.") from exc

    def head_object(self, key: str) -> dict:
        try:
            return self._client().head_object(
                Bucket=self.bucket_name,
                Key=key,
            )
        except (BotoCoreError, ClientError) as exc:
            raise R2StorageError("업로드된 R2 파일을 확인하지 못했습니다.") from exc

    def open_object(self, key: str) -> BinaryIO:
        try:
            response = self._client().get_object(
                Bucket=self.bucket_name,
                Key=key,
            )
            return response["Body"]
        except (BotoCoreError, ClientError, KeyError) as exc:
            raise R2StorageError("업로드된 R2 파일을 읽지 못했습니다.") from exc

    def iter_object_chunks(self, key: str, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        body = self.open_object(key)
        try:
            while True:
                chunk = body.read(chunk_size)
                if not chunk:
                    break
                yield bytes(chunk)
        except (BotoCoreError, ClientError, OSError) as exc:
            raise R2StorageError("R2 파일 스트림을 읽지 못했습니다.") from exc
        finally:
            close = getattr(body, "close", None)
            if close is not None:
                close()

    def get_object_range(self, key: str, start: int, end: int) -> bytes:
        try:
            response = self._client().get_object(
                Bucket=self.bucket_name,
                Key=key,
                Range=f"bytes={start}-{end}",
            )
            return bytes(response["Body"].read())
        except (BotoCoreError, ClientError, KeyError, OSError) as exc:
            raise R2StorageError("R2 파일 범위를 읽지 못했습니다.") from exc

    def put_object(self, *, key: str, content: bytes, content_type: str) -> None:
        try:
            self._client().put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=content,
                ContentType=content_type,
            )
        except (BotoCoreError, ClientError) as exc:
            raise R2StorageError("R2 파일을 저장하지 못했습니다.") from exc

    def delete_object(self, key: str) -> None:
        try:
            self._client().delete_object(
                Bucket=self.bucket_name,
                Key=key,
            )
        except (BotoCoreError, ClientError) as exc:
            raise R2StorageError("R2 파일을 정리하지 못했습니다.") from exc


r2_storage = R2StorageService()
rag_r2_storage = R2StorageService(storage_settings.rag_r2_bucket_name)
