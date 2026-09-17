import asyncio
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from time import time
from unittest.mock import patch

from fastapi import UploadFile
from sqlalchemy import create_engine, select

from app.schemas.admin import OcrDocumentResponse
from app.services.ocr_job_service import OcrJobManager, OcrJobNotFoundError
from app.services.ocr_job_store import SqlOcrJobStore


def result():
    return OcrDocumentResponse(
        documentName="공유 시험.txt", pageCount=1, characterCount=8,
        estimatedChunks=1, confidence=100, extractedText="공유 OCR 결과",
        chunks=["공유 OCR 결과"], readiness="ready", notes=[],
        chunk_artifact_key="synthetic/chunks.jsonl",
        original_object_key="synthetic/source.txt",
    )


class SharedOcrJobsTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        url = f"sqlite:///{Path(folder.name) / 'jobs.db'}"
        self.engines = [create_engine(url), create_engine(url)]
        for engine in self.engines:
            self.addCleanup(engine.dispose)
        self.stores = [SqlOcrJobStore(engine) for engine in self.engines]

    def manager(self, processor, index=0):
        return OcrJobManager(processor, 1024, 2, 10, store=self.stores[index])

    def test_other_instance_sees_queued_progress_and_complete_result(self):
        async def scenario():
            release = asyncio.Event()
            progress_seen = asyncio.Event()

            async def processor(file, chunk_size, overlap, progress):
                progress("extracting", 40, "합성 문서 처리 중")
                progress_seen.set()
                await release.wait()
                return result()

            writer = self.manager(processor)
            reader = self.manager(processor, 1)
            created = await writer.create_job(UploadFile(BytesIO(b"test"), filename="test.txt"), 100, 10)
            self.assertEqual(reader.get_job(created.job_id).status, "queued")
            await progress_seen.wait()
            self.assertEqual(reader.get_job(created.job_id).progress, 40)
            release.set()
            await writer._tasks[created.job_id]
            actual = reader.get_job(created.job_id)
            self.assertEqual(actual.status, "completed")
            self.assertEqual(actual.result, result())
            self.assertNotIn("chunk_artifact_key", actual.model_dump()["result"])
            self.assertNotIn("original_object_key", actual.model_dump()["result"])
            # 조회 결과 변경이 저장된 결과를 덮어쓰지 않아야 한다.
            actual.result.chunks.clear()
            self.assertEqual(reader.get_job(created.job_id).result.chunks, result().chunks)
            # 작업 실행 프로세스의 메모리가 비워진 뒤에도 결과는 남는다.
            writer._jobs.clear()
            self.assertEqual(reader.get_job(created.job_id).result, result())

        asyncio.run(scenario())

    def test_failed_status_is_shared(self):
        async def scenario():
            async def processor(*args):
                raise ValueError("synthetic failure")

            writer = self.manager(processor)
            reader = self.manager(processor, 1)
            created = await writer.create_job(UploadFile(BytesIO(b"test")), 100, 10)
            await writer._tasks[created.job_id]
            actual = reader.get_job(created.job_id)
            self.assertEqual(actual.status, "failed")
            self.assertIn("예상하지 못한 오류", actual.error)

        asyncio.run(scenario())

    def test_expiry_is_shared_and_cleanup_only_removes_expired_records(self):
        writer = self.manager(None)
        reader = self.manager(None, 1)
        expired_id = writer._reserve_job()
        active_id = writer._reserve_job()
        self.stores[0].put(writer.get_job(expired_id), time() - 1)
        with self.assertRaises(OcrJobNotFoundError):
            reader.get_job(expired_id)
        self.stores[1].remove_expired()
        self.assertEqual(reader.get_job(active_id).status, "queued")
        with self.engines[1].connect() as connection:
            remaining = connection.execute(select(self.stores[1].table.c.job_id)).scalars().all()
        self.assertEqual(remaining, [active_id])

    def test_storage_outage_is_not_misreported_as_missing_job(self):
        reader = self.manager(None)
        with patch.object(self.stores[0], "get", side_effect=RuntimeError("storage offline")):
            with self.assertRaisesRegex(RuntimeError, "storage offline"):
                reader.get_job("unknown")

    def test_failed_initial_write_does_not_accept_or_start_job(self):
        async def scenario():
            writer = self.manager(None)
            with patch.object(self.stores[0], "put", side_effect=RuntimeError("storage offline")):
                with self.assertRaisesRegex(RuntimeError, "storage offline"):
                    await writer.create_job(UploadFile(BytesIO(b"test")), 100, 10)
            self.assertEqual(writer._jobs, {})
            self.assertEqual(writer._tasks, {})

        asyncio.run(scenario())

    def test_unknown_job_is_missing_on_other_instance(self):
        with self.assertRaises(OcrJobNotFoundError):
            self.manager(None, 1).get_job("unknown")

    def test_cancelled_worker_reports_failure_to_other_instance(self):
        async def scenario():
            async def processor(*args):
                await asyncio.Event().wait()

            writer = self.manager(processor)
            reader = self.manager(processor, 1)
            created = await writer.create_job(UploadFile(BytesIO(b"test")), 100, 10)
            task = writer._tasks[created.job_id]
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            actual = reader.get_job(created.job_id)
            self.assertEqual(actual.status, "failed")
            self.assertIn("서버 종료", actual.error)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
