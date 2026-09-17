"""OCR 실행은 현재 프로세스가 담당하고 상태·결과는 공용 저장소에 보관합니다."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO
from threading import RLock
from uuid import uuid4

from fastapi import UploadFile
from starlette.datastructures import Headers

from ai.ocr.contracts import ProgressCallback
from ai.ocr.errors import DocumentTooLargeError, OcrError
from app.core.config import settings
from app.schemas.admin import (
    OcrDocumentResponse,
    OcrJobCreatedResponse,
    OcrJobStatusResponse,
)
from app.services.large_document_service import large_document_service
from app.services.ocr_workflow import process_document
from app.services.ocr_job_store import SqlOcrJobStore, create_shared_job_store
from app.services.r2_storage import R2StorageError
from app.services.web_document_fetcher import normalize_web_url
from app.services.web_ocr_workflow import process_web_url

logger = logging.getLogger(__name__)


class OcrJobNotFoundError(Exception):
    """요청한 OCR Job이 없거나 만료되었을 때 발생합니다."""


class OcrJobCapacityError(Exception):
    """동시에 보관할 수 있는 OCR Job 수를 초과했을 때 발생합니다."""


OcrProcessor = Callable[
    [UploadFile, int, int, ProgressCallback | None],
    Awaitable[OcrDocumentResponse],
]
UrlOcrProcessor = Callable[
    [str, int, int, ProgressCallback | None],
    Awaitable[OcrDocumentResponse],
]
RemoteOcrProcessor = Callable[..., Awaitable[OcrDocumentResponse]]


@dataclass
class OcrJobRecord:
    job_id: str
    status: str
    stage: str
    progress: int
    message: str
    created_at: datetime
    updated_at: datetime
    result: OcrDocumentResponse | None = None
    error: str | None = None


class OcrJobManager:
    """로컬 실행 작업과 인스턴스 간 공유되는 조회 상태를 관리합니다."""

    def __init__(
        self,
        processor: OcrProcessor,
        max_file_bytes: int,
        max_pending_jobs: int,
        ttl_minutes: int,
        url_processor: UrlOcrProcessor | None = None,
        remote_processor: RemoteOcrProcessor | None = None,
        store: SqlOcrJobStore | None = None,
    ) -> None:
        self.processor = processor
        self.max_file_bytes = max_file_bytes
        self.max_pending_jobs = max_pending_jobs
        self.ttl = timedelta(minutes=ttl_minutes)
        self.url_processor = url_processor
        self.remote_processor = remote_processor
        self.store = store
        self._jobs: dict[str, OcrJobRecord] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = RLock()

    async def create_job(
        self,
        file: UploadFile,
        chunk_size: int,
        overlap: int,
    ) -> OcrJobCreatedResponse:
        """업로드 내용을 안전하게 복사한 뒤 백그라운드 OCR 작업을 시작합니다."""

        # 요청이 끝나면 원본 UploadFile이 닫히므로 Job용 byte 복사본을 먼저 만듭니다.
        content = await file.read(self.max_file_bytes + 1)
        if len(content) > self.max_file_bytes:
            max_size_mb = self.max_file_bytes // (1024 * 1024)
            raise DocumentTooLargeError(
                f"파일 크기는 {max_size_mb}MB 이하여야 합니다."
            )

        job_id = self._reserve_job()

        task = asyncio.create_task(
            self._run_job(
                job_id=job_id,
                content=content,
                file_name=file.filename or "",
                content_type=file.content_type or "application/octet-stream",
                chunk_size=chunk_size,
                overlap=overlap,
            )
        )
        with self._lock:
            self._tasks[job_id] = task
        task.add_done_callback(lambda _task: self._discard_task(job_id))

        return OcrJobCreatedResponse(jobId=job_id, status="queued")

    async def create_url_job(
        self,
        url: str,
        chunk_size: int,
        overlap: int,
    ) -> OcrJobCreatedResponse:
        """검증된 URL을 파일 Job과 같은 메모리 대기열에서 처리합니다."""

        if self.url_processor is None:
            raise RuntimeError("웹 URL OCR Processor가 설정되지 않았습니다.")
        normalized_url = normalize_web_url(url, settings.ocr_web_max_url_length)
        job_id = self._reserve_job()
        task = asyncio.create_task(
            self._run_url_job(job_id, normalized_url, chunk_size, overlap)
        )
        with self._lock:
            self._tasks[job_id] = task
        task.add_done_callback(lambda _task: self._discard_task(job_id))
        return OcrJobCreatedResponse(jobId=job_id, status="queued")

    async def create_remote_job(
        self,
        *,
        object_key: str,
        file_name: str,
        file_size: int,
        content_type: str,
        chunk_size: int,
        overlap: int,
    ) -> OcrJobCreatedResponse:
        """R2 업로드 원본을 요청 본문으로 복사하지 않고 백그라운드 분석합니다."""

        if self.remote_processor is None:
            raise RuntimeError("대용량 OCR Processor가 설정되지 않았습니다.")
        job_id = self._reserve_job()
        task = asyncio.create_task(
            self._run_remote_job(
                job_id=job_id,
                object_key=object_key,
                file_name=file_name,
                file_size=file_size,
                content_type=content_type,
                chunk_size=chunk_size,
                overlap=overlap,
            )
        )
        with self._lock:
            self._tasks[job_id] = task
        task.add_done_callback(lambda _task: self._discard_task(job_id))
        return OcrJobCreatedResponse(jobId=job_id, status="queued")

    def get_job(self, job_id: str) -> OcrJobStatusResponse:
        """Frontend polling에 사용할 현재 Job 상태의 복사본을 반환합니다."""

        # 메모리 캐시를 읽으면 다른 인스턴스의 업데이트를 놓칠 수 있으므로,
        # 배포 환경에서는 등록·진행 조회·VectorDB 저장이 같은 저장소를 사용한다.
        if self.store is not None:
            status = self.store.get(job_id)
            if status is None:
                raise OcrJobNotFoundError("OCR 작업을 찾을 수 없거나 만료되었습니다.")
            return status

        now = datetime.now(UTC)
        with self._lock:
            self._remove_expired_jobs(now)
            job = self._jobs.get(job_id)
            if job is None:
                raise OcrJobNotFoundError("OCR 작업을 찾을 수 없거나 만료되었습니다.")
            return _build_status_response(job)

    async def _run_job(
        self,
        job_id: str,
        content: bytes,
        file_name: str,
        content_type: str,
        chunk_size: int,
        overlap: int,
    ) -> None:
        upload_file = UploadFile(
            file=BytesIO(content),
            filename=file_name,
            headers=Headers({"content-type": content_type}),
        )
        self._update_progress(
            job_id,
            stage="uploading",
            progress=5,
            message="파일 업로드가 완료되었습니다.",
        )

        try:
            result = await self.processor(
                upload_file,
                chunk_size,
                overlap,
                lambda stage, progress, message: self._update_progress(
                    job_id,
                    stage,
                    progress,
                    message,
                ),
            )
        except OcrError as exc:
            logger.warning("OCR Job 실패: job_id=%s, error=%s", job_id, exc)
            self._fail_job(job_id, str(exc))
        except Exception:
            logger.exception("예상하지 못한 OCR Job 오류: job_id=%s", job_id)
            self._fail_job(job_id, "문서 분석 중 예상하지 못한 오류가 발생했습니다.")
        else:
            self._complete_job(job_id, result)
        finally:
            await upload_file.close()

    async def _run_url_job(
        self,
        job_id: str,
        url: str,
        chunk_size: int,
        overlap: int,
    ) -> None:
        self._update_progress(
            job_id,
            stage="validating_url",
            progress=5,
            message="웹페이지 URL 형식을 확인했습니다.",
        )
        try:
            assert self.url_processor is not None
            result = await self.url_processor(
                url,
                chunk_size,
                overlap,
                lambda stage, progress, message: self._update_progress(
                    job_id, stage, progress, message
                ),
            )
        except OcrError as exc:
            logger.warning("Web OCR Job 실패: job_id=%s, error=%s", job_id, exc)
            self._fail_job(job_id, str(exc))
        except Exception:
            logger.exception("예상하지 못한 Web OCR Job 오류: job_id=%s", job_id)
            self._fail_job(job_id, "웹페이지 분석 중 예상하지 못한 오류가 발생했습니다.")
        else:
            self._complete_job(job_id, result)

    async def _run_remote_job(
        self,
        *,
        job_id: str,
        object_key: str,
        file_name: str,
        file_size: int,
        content_type: str,
        chunk_size: int,
        overlap: int,
    ) -> None:
        self._update_progress(
            job_id,
            stage="uploading",
            progress=5,
            message="R2 직접 업로드가 완료되었습니다.",
        )
        try:
            assert self.remote_processor is not None
            result = await self.remote_processor(
                object_key=object_key,
                file_name=file_name,
                file_size=file_size,
                content_type=content_type,
                chunk_size=chunk_size,
                overlap=overlap,
                progress_callback=lambda stage, progress, message: self._update_progress(
                    job_id,
                    stage,
                    progress,
                    message,
                ),
            )
        except OcrError as exc:
            logger.warning("대용량 OCR Job 실패: job_id=%s, error=%s", job_id, exc)
            self._fail_job(job_id, str(exc))
        except R2StorageError as exc:
            logger.warning("대용량 OCR R2 실패: job_id=%s, error=%s", job_id, exc)
            self._fail_job(job_id, str(exc))
        except Exception:
            logger.exception("예상하지 못한 대용량 OCR Job 오류: job_id=%s", job_id)
            self._fail_job(job_id, "대용량 문서 분석 중 예상하지 못한 오류가 발생했습니다.")
        else:
            self._complete_job(job_id, result)

    def _reserve_job(self) -> str:
        now = datetime.now(UTC)
        job_id = uuid4().hex
        if self.store is not None:
            self.store.remove_expired()
        with self._lock:
            self._remove_expired_jobs(now)
            active_job_count = sum(
                job.status in {"queued", "processing"}
                for job in self._jobs.values()
            )
            if active_job_count >= self.max_pending_jobs:
                raise OcrJobCapacityError(
                    "동시에 처리할 수 있는 OCR 작업 수를 초과했습니다. 잠시 후 다시 시도해 주세요."
                )
            self._jobs[job_id] = OcrJobRecord(
                job_id=job_id,
                status="queued",
                stage="queued",
                progress=3,
                message="OCR 작업이 대기열에 등록되었습니다.",
                created_at=now,
                updated_at=now,
            )
            try:
                # 202를 반환하기 전에 다른 인스턴스도 읽을 수 있어야 한다.
                self._persist_job(self._jobs[job_id])
            except Exception:
                self._jobs.pop(job_id, None)
                raise
        return job_id

    def _update_progress(
        self,
        job_id: str,
        stage: str,
        progress: int,
        message: str,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status in {"completed", "failed"}:
                return
            job.status = "processing"
            job.stage = stage
            job.progress = max(job.progress, min(progress, 99))
            job.message = message
            job.updated_at = datetime.now(UTC)
            self._persist_job(job)

    def _complete_job(self, job_id: str, result: OcrDocumentResponse) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "completed"
            job.stage = "completed"
            job.progress = 100
            job.message = "문서 분석이 완료되었습니다."
            job.result = result
            job.updated_at = datetime.now(UTC)
            self._persist_job(job)

    def _fail_job(self, job_id: str, error: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "failed"
            job.stage = "failed"
            job.message = "문서 분석에 실패했습니다."
            job.error = error
            job.updated_at = datetime.now(UTC)
            self._persist_job(job)

    def _persist_job(self, job: OcrJobRecord) -> None:
        if self.store is None:
            return
        # 정상 완료 후에는 기존 TTL을 적용한다. 실행 인스턴스가 강제 종료된
        # 작업도 영구 잔류하지 않도록 진행 중 상태에는 최소 24시간 TTL을 둔다.
        ttl = self.ttl if job.status in {"completed", "failed"} else max(self.ttl, timedelta(hours=24))
        self.store.put(_build_status_response(job), (job.updated_at + ttl).timestamp())

    def _discard_task(self, job_id: str) -> None:
        with self._lock:
            task = self._tasks.pop(job_id, None)
        if task is None:
            return
        try:
            if task.cancelled():
                self._fail_job(job_id, "서버 종료로 OCR 작업이 중단되었습니다. 파일을 다시 분석해 주세요.")
            elif task.exception() is not None:
                logger.error("OCR 작업 상태 저장 실패: job_id=%s", job_id, exc_info=task.exception())
                self._fail_job(job_id, "OCR 작업 상태를 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.")
        except Exception:
            logger.exception("OCR 종료 상태를 저장하지 못했습니다: job_id=%s", job_id)

    def _remove_expired_jobs(self, now: datetime) -> None:
        expired_job_ids = [
            job_id
            for job_id, job in self._jobs.items()
            if job.status in {"completed", "failed"} and now - job.updated_at > self.ttl
        ]
        for job_id in expired_job_ids:
            self._jobs.pop(job_id, None)


def _build_status_response(job: OcrJobRecord) -> OcrJobStatusResponse:
    return OcrJobStatusResponse(
        jobId=job.job_id,
        status=job.status,
        stage=job.stage,
        progress=job.progress,
        message=job.message,
        result=job.result,
        error=job.error,
    )


ocr_job_manager = OcrJobManager(
    processor=process_document,
    max_file_bytes=settings.ocr_inline_file_size_mb * 1024 * 1024,
    max_pending_jobs=settings.ocr_max_pending_jobs,
    ttl_minutes=settings.ocr_job_ttl_minutes,
    url_processor=process_web_url,
    remote_processor=large_document_service.process,
    store=create_shared_job_store(),
)
