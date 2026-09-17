import asyncio
import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.document_repository import (
    DocumentPersistenceError,
    DocumentRepository,
    SavedDocument,
)
from app.schemas.admin import OcrDocumentResponse, OcrVectorSaveRequest
from app.services.admin_ocr import (
    OcrSaveValidationError,
    _build_job_file_reference,
    save_ocr_result_with_embeddings,
)
from app.services.embedding_service import (
    EmbeddingBatch,
    EmbeddingGenerationError,
    EmbeddingValidationError,
    RemoteDualEmbeddingService,
    create_embedding_service,
)


class RemoteDualEmbeddingServiceTest(unittest.TestCase):
    def test_settings_create_jina_and_bge_service(self) -> None:
        service = create_embedding_service(_embedding_settings())

        self.assertIsInstance(service, RemoteDualEmbeddingService)
        self.assertEqual(service.provider, "remote-dual")
        self.assertEqual(service.models, ("jina-v4", "medical-bgem3"))
        self.assertEqual(service.dimension, 1024)

    def test_empty_chunk_is_rejected_before_remote_call(self) -> None:
        service = create_embedding_service(_embedding_settings())
        with self.assertRaises(EmbeddingValidationError):
            asyncio.run(service.embed_chunks(["정상", "  "]))


class DocumentRepositoryTest(unittest.TestCase):
    def test_document_and_all_chunks_are_committed_together(self) -> None:
        document_id = uuid4()
        db = FakeSession(document_id=document_id)
        repository = DocumentRepository(db)  # type: ignore[arg-type]

        saved = repository.save_with_chunks(
            original_file_url="ocr-job://job/sample.pdf",
            extracted_text="전체 텍스트",
            chunks=["첫 Chunk", "둘째 Chunk"],
            embeddings_by_provider={
                "jina-v4": [[0.1] * 1024, [0.2] * 1024],
                "medical-bgem3": [[0.3] * 1024, [0.4] * 1024],
            },
        )

        self.assertEqual(saved, SavedDocument(document_id=document_id, chunk_count=2))
        self.assertTrue(db.committed)
        self.assertFalse(db.rolled_back)
        self.assertEqual([row.chunk_index for row in db.chunk_rows], [0, 1])
        self.assertTrue(all(row.document_id == document_id for row in db.chunk_rows))
        self.assertEqual([row.chunk_text for row in db.chunk_rows], ["첫 Chunk", "둘째 Chunk"])
        self.assertEqual(len(db.embedding_rows), 4)
        self.assertEqual(
            {row.provider_name for row in db.embedding_rows},
            {"jina-v4", "medical-bgem3"},
        )
        self.assertTrue(all(row.dimension == 1024 for row in db.embedding_rows))
        self.assertTrue(all(len(row.embedding) == 1024 for row in db.embedding_rows))

    def test_chunk_metadata_is_applied_to_every_chunk_when_given(self) -> None:
        document_id = uuid4()
        db = FakeSession(document_id=document_id)
        repository = DocumentRepository(db)  # type: ignore[arg-type]
        metadata = {"source": "https://health.kdca.go.kr/x", "source_tier": 2}

        repository.save_with_chunks(
            original_file_url="https://health.kdca.go.kr/x",
            extracted_text="전체 텍스트",
            chunks=["첫 Chunk", "둘째 Chunk"],
            embeddings_by_provider={
                "jina-v4": [[0.1] * 1024, [0.2] * 1024],
                "medical-bgem3": [[0.3] * 1024, [0.4] * 1024],
            },
            chunk_metadata=metadata,
        )

        self.assertTrue(all(row.chunk_metadata == metadata for row in db.chunk_rows))

    def test_omitting_chunk_metadata_leaves_it_none(self) -> None:
        # 기존 파일 업로드 호출부(chunk_metadata 인자 없이 호출)가 그대로 동작해야 한다.
        document_id = uuid4()
        db = FakeSession(document_id=document_id)
        repository = DocumentRepository(db)  # type: ignore[arg-type]

        repository.save_with_chunks(
            original_file_url="ocr-job://job/sample.pdf",
            extracted_text="전체 텍스트",
            chunks=["Chunk"],
            embeddings_by_provider={
                "jina-v4": [[0.1] * 1024],
                "medical-bgem3": [[0.2] * 1024],
            },
        )

        self.assertTrue(all(row.chunk_metadata is None for row in db.chunk_rows))

    def test_db_failure_rolls_back_whole_save(self) -> None:
        db = FakeSession(document_id=uuid4(), fail_commit=True)
        repository = DocumentRepository(db)  # type: ignore[arg-type]

        with self.assertRaises(DocumentPersistenceError):
            repository.save_with_chunks(
                original_file_url="ocr-job://job/sample.pdf",
                extracted_text="전체 텍스트",
                chunks=["Chunk"],
                embeddings_by_provider={
                    "jina-v4": [[0.1] * 1024],
                    "medical-bgem3": [[0.2] * 1024],
                },
            )

        self.assertFalse(db.committed)
        self.assertTrue(db.rolled_back)


class OcrVectorSaveFlowTest(unittest.TestCase):
    def test_completed_job_uses_existing_chunks_and_returns_saved_result(self) -> None:
        async def scenario() -> None:
            job_manager = Mock()
            job_manager.get_job.return_value = SimpleNamespace(
                status="completed",
                result=_ocr_result(),
            )
            embedder = FakeEmbedder()
            repository = FakeRepository()
            document_id = uuid4()
            repository.result = SavedDocument(document_id=document_id, chunk_count=2)

            response = await save_ocr_result_with_embeddings(
                OcrVectorSaveRequest(jobId="completed-job"),
                Mock(spec=Session, **{"scalars.return_value": []}),
                job_manager=job_manager,
                embedder=embedder,  # type: ignore[arg-type]
                repository=repository,
            )

            self.assertEqual(embedder.received_chunks, [_FIRST_CHUNK, _SECOND_CHUNK])
            self.assertEqual(repository.saved["chunks"], [_FIRST_CHUNK, _SECOND_CHUNK])
            self.assertEqual(response.document_id, document_id)
            self.assertEqual(response.chunk_count, 2)
            self.assertEqual(response.embedding_provider, "remote-dual")
            self.assertEqual(response.embedding_dimension, 1024)

        asyncio.run(scenario())

    def test_non_1024_provider_is_rejected_before_repository(self) -> None:
        async def scenario() -> None:
            job_manager = Mock()
            job_manager.get_job.return_value = SimpleNamespace(
                status="completed",
                result=_ocr_result(),
            )
            repository = FakeRepository()
            embedder = FakeEmbedder(dimension=768)

            with self.assertRaises(EmbeddingValidationError) as raised:
                await save_ocr_result_with_embeddings(
                    OcrVectorSaveRequest(jobId="completed-job"),
                    Mock(spec=Session, **{"scalars.return_value": []}),
                    job_manager=job_manager,
                    embedder=embedder,  # type: ignore[arg-type]
                    repository=repository,
                )

            self.assertIn("VECTOR(1024)", str(raised.exception))
            self.assertEqual(repository.saved, {})

        asyncio.run(scenario())

    def test_wrong_vector_from_provider_is_rejected_before_repository(self) -> None:
        async def scenario() -> None:
            job_manager = Mock()
            job_manager.get_job.return_value = SimpleNamespace(
                status="completed",
                result=_ocr_result(),
            )
            repository = FakeRepository()
            embedder = FakeEmbedder(vector_dimension=128)

            with self.assertRaises(EmbeddingValidationError) as raised:
                await save_ocr_result_with_embeddings(
                    OcrVectorSaveRequest(jobId="completed-job"),
                    Mock(spec=Session, **{"scalars.return_value": []}),
                    job_manager=job_manager,
                    embedder=embedder,  # type: ignore[arg-type]
                    repository=repository,
                )

            self.assertIn("Chunk 0", str(raised.exception))
            self.assertIn("128", str(raised.exception))
            self.assertEqual(repository.saved, {})

        asyncio.run(scenario())

    def test_embedding_failure_stops_before_db_save(self) -> None:
        async def scenario() -> None:
            job_manager = Mock()
            job_manager.get_job.return_value = SimpleNamespace(
                status="completed",
                result=_ocr_result(),
            )
            repository = FakeRepository()
            embedder = FakeEmbedder(error=EmbeddingGenerationError("실패"))

            with self.assertRaises(EmbeddingGenerationError):
                await save_ocr_result_with_embeddings(
                    OcrVectorSaveRequest(jobId="completed-job"),
                    Mock(spec=Session, **{"scalars.return_value": []}),
                    job_manager=job_manager,
                    embedder=embedder,  # type: ignore[arg-type]
                    repository=repository,
                )
            self.assertEqual(repository.saved, {})

        asyncio.run(scenario())

    def test_incomplete_job_is_rejected(self) -> None:
        job_manager = Mock()
        job_manager.get_job.return_value = SimpleNamespace(status="processing", result=None)
        with self.assertRaises(OcrSaveValidationError):
            asyncio.run(
                save_ocr_result_with_embeddings(
                    OcrVectorSaveRequest(jobId="processing-job"),
                    Mock(spec=Session, **{"scalars.return_value": []}),
                    job_manager=job_manager,
                )
            )

    def test_original_file_reference_falls_back_within_column_length(self) -> None:
        reference = _build_job_file_reference("job-id", "가" * 600 + ".pdf")
        self.assertTrue(reference.startswith("ocr-job://job-id/"))
        self.assertLessEqual(len(reference), 500)

    def test_url_job_keeps_existing_embedding_flow_and_saves_final_url(self) -> None:
        async def scenario() -> None:
            job_manager = Mock()
            url_result = _ocr_result().model_copy(
                update={
                    "source_type": "url",
                    "source_url": "https://example.com/final",
                }
            )
            job_manager.get_job.return_value = SimpleNamespace(
                status="completed", result=url_result
            )
            embedder = FakeEmbedder()
            repository = FakeRepository()

            await save_ocr_result_with_embeddings(
                OcrVectorSaveRequest(jobId="url-job"),
                Mock(spec=Session, **{"scalars.return_value": []}),
                job_manager=job_manager,
                embedder=embedder,  # type: ignore[arg-type]
                repository=repository,
            )

            self.assertEqual(embedder.received_chunks, [_FIRST_CHUNK, _SECOND_CHUNK])
            self.assertEqual(
                repository.saved["original_file_url"],
                "https://example.com/final",
            )

        asyncio.run(scenario())

    def test_url_job_chunk_metadata_carries_source_without_tier(self) -> None:
        # 2026-09-03: 관리자 업로드 청크도 RAG 검색 출처 표시를 받을 수 있어야
        # 한다(document_chunk.py의 search_by_provider 필터를 dataset_import와
        # 합치면서, chunk_metadata가 아예 안 채워지던 관리자 업로드 경로가 그대로면
        # 출처 표시를 영영 못 받는 문제를 같이 고쳤다).
        # 2026-09-04: source_tier(신뢰도 부스트)는 일부러 안 채운다 - "관리자가
        # URL을 직접 골랐다"는 사실이 "품질이 검증됐다"는 뜻은 아니다(admin_ocr.py
        # _build_chunk_metadata 참고).
        async def scenario() -> None:
            job_manager = Mock()
            url_result = _ocr_result().model_copy(
                update={"source_type": "url", "source_url": "https://health.kdca.go.kr/x"}
            )
            job_manager.get_job.return_value = SimpleNamespace(status="completed", result=url_result)
            repository = FakeRepository()

            await save_ocr_result_with_embeddings(
                OcrVectorSaveRequest(jobId="url-job"),
                Mock(spec=Session, **{"scalars.return_value": []}),
                job_manager=job_manager,
                embedder=FakeEmbedder(),  # type: ignore[arg-type]
                repository=repository,
            )

            self.assertEqual(
                repository.saved["chunk_metadata"],
                {"source": "https://health.kdca.go.kr/x", "needs_review": False},
            )

        asyncio.run(scenario())

    def test_file_job_chunk_metadata_carries_filename_as_source(self) -> None:
        # 2026-09-04: 파일 업로드도 URL과 같은 이유로 원본 파일명을 source로
        # 남긴다(출처 추적용, 신뢰도 판단 아님) - document_name은 OcrDocumentResponse가
        # 항상 채우는 필드라 URL만큼 안정적으로 얻을 수 있다.
        async def scenario() -> None:
            job_manager = Mock()
            job_manager.get_job.return_value = SimpleNamespace(status="completed", result=_ocr_result())
            repository = FakeRepository()

            await save_ocr_result_with_embeddings(
                OcrVectorSaveRequest(jobId="completed-job"),
                Mock(spec=Session, **{"scalars.return_value": []}),
                job_manager=job_manager,
                embedder=FakeEmbedder(),  # type: ignore[arg-type]
                repository=repository,
            )

            self.assertEqual(
                repository.saved["chunk_metadata"], {"source": "sample.pdf", "needs_review": False}
            )

        asyncio.run(scenario())

    def test_risky_keyword_marks_needs_review_true(self) -> None:
        # 2026-09-07: HF/KDCA와 같은 기준(ai/rag/ingestion/quality.detect_needs_review)으로
        # 관리자 업로드도 위험 키워드(용량/처방/응급 등)가 있으면 표시해둔다 -
        # scripts/report_needs_review.py가 그대로 같이 집계할 수 있게.
        async def scenario() -> None:
            job_manager = Mock()
            risky_result = _ocr_result().model_copy(
                update={"extracted_text": "이 약의 권장 용량은 성인 기준 1일 2회입니다."}
            )
            job_manager.get_job.return_value = SimpleNamespace(status="completed", result=risky_result)
            repository = FakeRepository()

            await save_ocr_result_with_embeddings(
                OcrVectorSaveRequest(jobId="completed-job"),
                Mock(spec=Session, **{"scalars.return_value": []}),
                job_manager=job_manager,
                embedder=FakeEmbedder(),  # type: ignore[arg-type]
                repository=repository,
            )

            self.assertTrue(repository.saved["chunk_metadata"]["needs_review"])

        asyncio.run(scenario())

    def test_chunk_already_in_db_is_skipped_and_noted_in_message(self) -> None:
        # 2026-09-07: 같은 파일을 실수로 두 번 올리거나, 이미 HF/KDCA로 들어가
        # 있는 내용과 겹치는 파일을 올려도 중복 저장되지 않아야 한다.
        async def scenario() -> None:
            job_manager = Mock()
            job_manager.get_job.return_value = SimpleNamespace(status="completed", result=_ocr_result())
            repository = FakeRepository()
            repository.result = SavedDocument(document_id=uuid4(), chunk_count=1)
            # _FIRST_CHUNK와 완전히 같은 텍스트가 이미 DB에 있다고 가정한다.
            db = Mock(spec=Session, **{"scalars.return_value": [_FIRST_CHUNK]})

            response = await save_ocr_result_with_embeddings(
                OcrVectorSaveRequest(jobId="completed-job"),
                db,
                job_manager=job_manager,
                embedder=FakeEmbedder(),  # type: ignore[arg-type]
                repository=repository,
            )

            self.assertEqual(repository.saved["chunks"], [_SECOND_CHUNK])
            self.assertIn("중복으로 1개 청크는 제외됨", response.message)

        asyncio.run(scenario())

    def test_repeated_chunk_within_same_upload_is_deduped_too(self) -> None:
        # 2026-09-07: DB에는 없어도 "이번에 올리는 문서 안에서" 같은 텍스트가
        # 반복되는 경우(페이지마다 반복되는 머리말/꼬리말 등)도 하나만 남겨야 한다 -
        # find_existing_chunk_texts는 DB에 있는 것만 알려주므로, 배치 내부의
        # 반복은 별도로 걸러야 한다.
        async def scenario() -> None:
            job_manager = Mock()
            repeated_result = _ocr_result().model_copy(
                update={"chunks": [_FIRST_CHUNK, _FIRST_CHUNK, _SECOND_CHUNK]}
            )
            job_manager.get_job.return_value = SimpleNamespace(status="completed", result=repeated_result)
            repository = FakeRepository()
            db = Mock(spec=Session, **{"scalars.return_value": []})  # DB엔 아직 아무것도 없음

            response = await save_ocr_result_with_embeddings(
                OcrVectorSaveRequest(jobId="completed-job"),
                db,
                job_manager=job_manager,
                embedder=FakeEmbedder(),  # type: ignore[arg-type]
                repository=repository,
            )

            self.assertEqual(repository.saved["chunks"], [_FIRST_CHUNK, _SECOND_CHUNK])
            self.assertIn("중복으로 1개 청크는 제외됨", response.message)

        asyncio.run(scenario())

    def test_broken_chunk_is_filtered_out_before_embedding_and_noted_in_message(self) -> None:
        # 2026-09-04: 임베딩 직전에 clean_content()로 깨진/쓰레기 청크를 걸러낸다 -
        # 나머지 정상 청크는 그대로 저장되고, 걸러진 개수는 응답 메시지에 남는다
        # (조용히 사라지지 않게).
        async def scenario() -> None:
            job_manager = Mock()
            broken_result = _ocr_result().model_copy(
                update={
                    "chunks": [_FIRST_CHUNK, "<div><script>a</script></div>", _SECOND_CHUNK],
                }
            )
            job_manager.get_job.return_value = SimpleNamespace(status="completed", result=broken_result)
            repository = FakeRepository()
            repository.result = SavedDocument(document_id=uuid4(), chunk_count=2)

            response = await save_ocr_result_with_embeddings(
                OcrVectorSaveRequest(jobId="completed-job"),
                Mock(spec=Session, **{"scalars.return_value": []}),
                job_manager=job_manager,
                embedder=FakeEmbedder(),  # type: ignore[arg-type]
                repository=repository,
            )

            self.assertEqual(repository.saved["chunks"], [_FIRST_CHUNK, _SECOND_CHUNK])
            self.assertIn("1개 청크는 제외됨", response.message)

        asyncio.run(scenario())

    def test_all_chunks_broken_raises_validation_error(self) -> None:
        async def scenario() -> None:
            job_manager = Mock()
            broken_result = _ocr_result().model_copy(update={"chunks": ["<script>x</script>"]})
            job_manager.get_job.return_value = SimpleNamespace(status="completed", result=broken_result)

            with self.assertRaises(OcrSaveValidationError):
                await save_ocr_result_with_embeddings(
                    OcrVectorSaveRequest(jobId="completed-job"),
                    Mock(spec=Session, **{"scalars.return_value": []}),
                    job_manager=job_manager,
                    embedder=FakeEmbedder(),  # type: ignore[arg-type]
                    repository=FakeRepository(),
                )

        asyncio.run(scenario())


class OcrVectorSaveApiTest(unittest.TestCase):
    def setUp(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.api.admin.router import router
        from app.api.auth.dependencies import require_admin
        from app.core.database import get_db

        app = FastAPI()
        app.include_router(router, prefix="/api/admin")
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session, **{"scalars.return_value": []})
        app.dependency_overrides[require_admin] = lambda: object()
        self.client = TestClient(app)

    def test_success_response_uses_camel_case_contract(self) -> None:
        document_id = uuid4()
        result = {
            "message": "저장 완료",
            "documentId": document_id,
            "chunkCount": 2,
            "embeddingProvider": "remote-dual",
            "embeddingDimension": 1024,
            "embeddingModel": "jina-v4 + medical-bgem3",
        }
        with patch(
            "app.api.admin.router.save_ocr_result_with_embeddings",
            new=AsyncMock(return_value=result),
        ):
            response = self.client.post(
                "/api/admin/ocr/vector-save",
                json={"jobId": "completed-job"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["documentId"], str(document_id))
        self.assertEqual(response.json()["embeddingProvider"], "remote-dual")
        self.assertEqual(response.json()["embeddingDimension"], 1024)

    def test_embedding_failure_is_not_reported_as_success(self) -> None:
        with patch(
            "app.api.admin.router.save_ocr_result_with_embeddings",
            new=AsyncMock(side_effect=EmbeddingGenerationError("Embedding 생성 실패")),
        ):
            response = self.client.post(
                "/api/admin/ocr/vector-save",
                json={"jobId": "completed-job"},
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "Embedding 생성 실패")

    def test_db_failure_is_not_reported_as_success(self) -> None:
        with patch(
            "app.api.admin.router.save_ocr_result_with_embeddings",
            new=AsyncMock(side_effect=DocumentPersistenceError("Neon 저장 실패")),
        ):
            response = self.client.post(
                "/api/admin/ocr/vector-save",
                json={"jobId": "completed-job"},
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"], "Neon 저장 실패")

    def test_vector_save_requires_admin_authentication(self) -> None:
        # 2026-09-07: /ocr/vector-save는 RAG 코퍼스에 직접 쓰는 엔드포인트인데
        # 서버 쪽 인증 검사가 전혀 없었다 - 이 회귀테스트로 다시 뚫리면 바로 걸린다.
        from app.api.auth.dependencies import require_admin

        self.client.app.dependency_overrides.pop(require_admin, None)
        response = self.client.post(
            "/api/admin/ocr/vector-save",
            json={"jobId": "completed-job"},
        )
        self.assertEqual(response.status_code, 401)


class FakeSession:
    def __init__(self, *, document_id, fail_commit: bool = False) -> None:
        self.document_id = document_id
        self.fail_commit = fail_commit
        self.document: Any | None = None
        self.chunk_rows = []
        self.embedding_rows = []
        self.committed = False
        self.rolled_back = False
        self.flush_count = 0

    def add(self, value) -> None:
        self.document = value

    def flush(self) -> None:
        if self.document is None:
            raise AssertionError("flush 전에 document가 추가되어야 합니다.")
        self.flush_count += 1
        if self.flush_count == 1:
            self.document.id = self.document_id
            return
        for row in self.chunk_rows:
            row.id = uuid4()

    def add_all(self, values) -> None:
        rows = list(values)
        if not self.chunk_rows:
            self.chunk_rows = rows
        else:
            self.embedding_rows = rows

    def commit(self) -> None:
        if self.fail_commit:
            raise RuntimeError("DB unavailable")
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class FakeEmbedder:
    provider = "remote-dual"
    model = "jina-v4 + medical-bgem3"
    models = ("jina-v4", "medical-bgem3")

    def __init__(
        self,
        error: Exception | None = None,
        *,
        dimension: int = 1024,
        vector_dimension: int | None = None,
    ) -> None:
        self.error = error
        self.dimension = dimension
        self.vector_dimension = vector_dimension or dimension
        self.received_chunks = []

    async def embed_chunks(self, chunks):
        self.received_chunks = chunks
        if self.error:
            raise self.error
        vectors = [
            [float(index)] * self.vector_dimension
            for index, _chunk in enumerate(chunks)
        ]
        return EmbeddingBatch(
            vectors_by_provider={
                "jina-v4": vectors,
                "medical-bgem3": [vector.copy() for vector in vectors],
            }
        )


class FakeRepository:
    def __init__(self) -> None:
        self.saved = {}
        self.result = SavedDocument(document_id=uuid4(), chunk_count=2)

    def save_with_chunks(self, **kwargs):
        self.saved = kwargs
        return self.result


def _embedding_settings() -> Settings:
    return Settings(
        _env_file=None,
        embedding_remote_base_url="https://embedding.test",
        embedding_api_key="test-api-key",
        embedding_jina_model="jina-v4",
        embedding_bge_model="medical-bgem3",
        embedding_dimension=1024,
        embedding_timeout_seconds=5,
        embedding_batch_size=32,
    )


_FIRST_CHUNK = "이것은 첫 번째 청크 예시 문장입니다"
_SECOND_CHUNK = "이것은 두 번째 청크 예시 문장입니다"


def _ocr_result() -> OcrDocumentResponse:
    return OcrDocumentResponse(
        documentName="sample.pdf",
        pageCount=1,
        characterCount=16,
        estimatedChunks=2,
        confidence=99.0,
        extractedText=f"{_FIRST_CHUNK}\n{_SECOND_CHUNK}",
        chunks=[_FIRST_CHUNK, _SECOND_CHUNK],
        readiness="ready",
        notes=[],
    )


if __name__ == "__main__":
    unittest.main()
