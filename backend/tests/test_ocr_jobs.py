import asyncio
import unittest
from io import BytesIO

from fastapi import UploadFile
from starlette.datastructures import Headers

from ai.ocr.errors import DocumentValidationError
from app.schemas.admin import OcrDocumentResponse
from app.services.ocr_job_service import (
    OcrJobCapacityError,
    OcrJobNotFoundError,
    OcrJobManager,
)


class OcrJobManagerTest(unittest.TestCase):
    def test_job_reports_progress_and_result(self) -> None:
        async def scenario() -> None:
            async def processor(file, chunk_size, overlap, progress_callback):
                self.assertEqual(file.filename, "sample.png")
                self.assertEqual((chunk_size, overlap), (200, 30))
                progress_callback("validating", 10, "파일 검증 중")
                await asyncio.sleep(0)
                progress_callback("extracting", 75, "OCR 처리 중")
                return _result()

            manager = _manager(processor)
            created = await manager.create_job(
                _upload(b"image-content"),
                chunk_size=200,
                overlap=30,
            )

            status = await _wait_for_terminal_status(manager, created.job_id)
            self.assertEqual(status.status, "completed")
            self.assertEqual(status.stage, "completed")
            self.assertEqual(status.progress, 100)
            self.assertIsNotNone(status.result)
            self.assertEqual(status.result.document_name, "sample.png")

        asyncio.run(scenario())

    def test_job_exposes_domain_error_as_failed_status(self) -> None:
        async def scenario() -> None:
            async def processor(_file, _chunk_size, _overlap, _progress_callback):
                raise DocumentValidationError("지원하지 않는 문서입니다.")

            manager = _manager(processor)
            created = await manager.create_job(
                _upload(b"invalid"),
                chunk_size=200,
                overlap=30,
            )

            status = await _wait_for_terminal_status(manager, created.job_id)
            self.assertEqual(status.status, "failed")
            self.assertEqual(status.error, "지원하지 않는 문서입니다.")
            self.assertLess(status.progress, 100)

        asyncio.run(scenario())

    def test_capacity_rejects_additional_active_job(self) -> None:
        async def scenario() -> None:
            release = asyncio.Event()

            async def processor(_file, _chunk_size, _overlap, _progress_callback):
                await release.wait()
                return _result()

            manager = _manager(processor, max_pending_jobs=1)
            first = await manager.create_job(
                _upload(b"first"),
                chunk_size=200,
                overlap=30,
            )

            with self.assertRaises(OcrJobCapacityError):
                await manager.create_job(
                    _upload(b"second"),
                    chunk_size=200,
                    overlap=30,
                )

            release.set()
            await _wait_for_terminal_status(manager, first.job_id)

        asyncio.run(scenario())

    def test_unknown_job_raises_not_found(self) -> None:
        async def processor(_file, _chunk_size, _overlap, _progress_callback):
            return _result()

        manager = _manager(processor)
        with self.assertRaises(OcrJobNotFoundError):
            manager.get_job("missing-job")

    def test_url_job_uses_same_status_contract(self) -> None:
        async def scenario() -> None:
            async def file_processor(_file, _chunk_size, _overlap, _callback):
                return _result()

            async def url_processor(url, chunk_size, overlap, progress_callback):
                self.assertEqual(url, "https://example.com/article")
                self.assertEqual((chunk_size, overlap), (300, 40))
                progress_callback("extracting", 60, "본문 추출 중")
                return _url_result()

            manager = OcrJobManager(
                processor=file_processor,
                max_file_bytes=1024,
                max_pending_jobs=2,
                ttl_minutes=10,
                url_processor=url_processor,
            )
            created = await manager.create_url_job(
                "https://example.com/article", 300, 40
            )
            status = await _wait_for_terminal_status(manager, created.job_id)
            self.assertEqual(status.status, "completed")
            self.assertEqual(status.result.source_type, "url")
            self.assertEqual(status.result.source_url, "https://example.com/article")

        asyncio.run(scenario())


def _manager(processor, max_pending_jobs: int = 2) -> OcrJobManager:
    return OcrJobManager(
        processor=processor,
        max_file_bytes=1024,
        max_pending_jobs=max_pending_jobs,
        ttl_minutes=10,
    )


def _upload(content: bytes) -> UploadFile:
    return UploadFile(
        file=BytesIO(content),
        filename="sample.png",
        headers=Headers({"content-type": "image/png"}),
    )


async def _wait_for_terminal_status(
    manager: OcrJobManager,
    job_id: str,
):
    for _ in range(50):
        status = manager.get_job(job_id)
        if status.status in {"completed", "failed"}:
            return status
        await asyncio.sleep(0.01)
    raise AssertionError("OCR Job이 제한 시간 안에 완료되지 않았습니다.")


def _result() -> OcrDocumentResponse:
    return OcrDocumentResponse(
        documentName="sample.png",
        pageCount=1,
        characterCount=10,
        estimatedChunks=1,
        confidence=95.0,
        extractedText="추출 텍스트",
        chunks=["추출 텍스트"],
        readiness="ready",
        notes=[],
    )


def _url_result() -> OcrDocumentResponse:
    return OcrDocumentResponse(
        documentName="테스트 웹페이지",
        pageCount=None,
        characterCount=10,
        estimatedChunks=1,
        confidence=100.0,
        extractedText="웹 추출 텍스트",
        chunks=["웹 추출 텍스트"],
        readiness="ready",
        notes=[],
        sourceType="url",
        sourceUrl="https://example.com/article",
    )


if __name__ == "__main__":
    unittest.main()
