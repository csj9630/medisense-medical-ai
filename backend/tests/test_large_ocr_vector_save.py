import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from sqlalchemy.orm import Session

from app.repositories.document_repository import SavedDocument
from app.schemas.admin import OcrDocumentResponse, OcrVectorSaveRequest
from app.services.admin_ocr import save_ocr_result_with_embeddings
from app.services.embedding_service import EmbeddingBatch


class LargeOcrVectorSaveTest(unittest.TestCase):
    def test_artifact_chunks_are_embedded_and_saved_in_batches(self) -> None:
        async def scenario() -> None:
            chunks = [f"이것은 예시 청크 번호 {index}번입니다" for index in range(35)]
            storage = FakeArtifactStorage(chunks)
            repository = FakeStagedRepository()
            embedder = FakeBatchEmbedder()
            job_manager = Mock()
            job_manager.get_job.return_value = SimpleNamespace(
                status="completed",
                result=OcrDocumentResponse(
                    documentName="data.jsonl",
                    pageCount=None,
                    characterCount=350,
                    estimatedChunks=len(chunks),
                    confidence=100,
                    extractedText="preview",
                    chunks=chunks[:20],
                    readiness="ready",
                    notes=[],
                    chunk_artifact_key="admin-rag-artifacts/chunks.jsonl",
                    original_object_key="admin-rag-uploads/id/data.jsonl",
                ),
            )

            response = await save_ocr_result_with_embeddings(
                OcrVectorSaveRequest(jobId="large-job"),
                Mock(spec=Session, **{"scalars.return_value": []}),
                job_manager=job_manager,
                embedder=embedder,  # type: ignore[arg-type]
                repository=repository,  # type: ignore[arg-type]
                storage=storage,  # type: ignore[arg-type]
            )

            self.assertEqual(embedder.batch_sizes, [32, 3])
            self.assertEqual(repository.start_indices, [0, 32])
            self.assertEqual(repository.saved_chunks, chunks)
            self.assertEqual(response.chunk_count, 35)
            self.assertEqual(storage.deleted, ["admin-rag-artifacts/chunks.jsonl"])
            self.assertTrue(repository.finished)

        asyncio.run(scenario())

    def test_url_source_chunk_metadata_is_identical_across_every_batch(self) -> None:
        # 2026-09-03: 8GB 스테이지드 저장은 청크를 배치 여러 개로 나눠서 저장하는데,
        # chunk_metadata(source/source_tier)는 문서 하나에 배치 수와 무관하게 항상
        # 같은 값이어야 한다 - 배치마다 다시 계산해서 값이 흔들리면 안 됨을 확인한다.
        async def scenario() -> None:
            chunks = [f"이것은 예시 청크 번호 {index}번입니다" for index in range(35)]
            storage = FakeArtifactStorage(chunks)
            repository = FakeStagedRepository()
            embedder = FakeBatchEmbedder()
            job_manager = Mock()
            job_manager.get_job.return_value = SimpleNamespace(
                status="completed",
                result=OcrDocumentResponse(
                    documentName="data.jsonl",
                    pageCount=None,
                    characterCount=350,
                    estimatedChunks=len(chunks),
                    confidence=100,
                    extractedText="preview",
                    chunks=chunks[:20],
                    readiness="ready",
                    notes=[],
                    chunk_artifact_key="admin-rag-artifacts/chunks.jsonl",
                    original_object_key="admin-rag-uploads/id/data.jsonl",
                    source_type="url",
                    source_url="https://health.kdca.go.kr/big-page",
                ),
            )

            await save_ocr_result_with_embeddings(
                OcrVectorSaveRequest(jobId="large-url-job"),
                Mock(spec=Session, **{"scalars.return_value": []}),
                job_manager=job_manager,
                embedder=embedder,  # type: ignore[arg-type]
                repository=repository,  # type: ignore[arg-type]
                storage=storage,  # type: ignore[arg-type]
            )

            self.assertEqual(len(repository.chunk_metadata_by_batch), 2)  # 35개 -> 배치 32+3
            expected = {"source": "https://health.kdca.go.kr/big-page", "needs_review": False}
            self.assertTrue(all(m == expected for m in repository.chunk_metadata_by_batch))

        asyncio.run(scenario())

    def test_broken_chunk_in_batch_is_filtered_and_counted(self) -> None:
        # 2026-09-04: 8GB 스트리밍 경로도 배치 단위로 clean_content() 필터를 거친다 -
        # 문서 전체를 메모리에 모으지 않고, 이미 만들어진 청크 하나하나만 검사한다.
        async def scenario() -> None:
            good_chunks = [f"이것은 예시 청크 번호 {index}번입니다" for index in range(3)]
            chunks = [good_chunks[0], "<script>x</script>", good_chunks[1], good_chunks[2]]
            storage = FakeArtifactStorage(chunks)
            repository = FakeStagedRepository()
            embedder = FakeBatchEmbedder()
            job_manager = Mock()
            job_manager.get_job.return_value = SimpleNamespace(
                status="completed",
                result=OcrDocumentResponse(
                    documentName="data.jsonl",
                    pageCount=None,
                    characterCount=100,
                    estimatedChunks=len(chunks),
                    confidence=100,
                    extractedText="preview",
                    chunks=chunks,
                    readiness="ready",
                    notes=[],
                    chunk_artifact_key="admin-rag-artifacts/chunks.jsonl",
                    original_object_key="admin-rag-uploads/id/data.jsonl",
                ),
            )

            response = await save_ocr_result_with_embeddings(
                OcrVectorSaveRequest(jobId="large-job"),
                Mock(spec=Session, **{"scalars.return_value": []}),
                job_manager=job_manager,
                embedder=embedder,  # type: ignore[arg-type]
                repository=repository,  # type: ignore[arg-type]
                storage=storage,  # type: ignore[arg-type]
            )

            self.assertEqual(repository.saved_chunks, good_chunks)
            self.assertEqual(response.chunk_count, 3)
            self.assertIn("1개 청크는 제외됨", response.message)

        asyncio.run(scenario())


class FakeArtifactStorage:
    def __init__(self, chunks: list[str]) -> None:
        self.content = b"".join(
            json.dumps({"text": chunk}).encode() + b"\n" for chunk in chunks
        )
        self.deleted: list[str] = []

    def iter_object_chunks(self, _key, chunk_size=1024 * 1024):
        for start in range(0, len(self.content), 41):
            yield self.content[start : start + 41]

    def delete_object(self, key):
        self.deleted.append(key)


class FakeStagedRepository:
    def __init__(self) -> None:
        self.document_id = uuid4()
        self.start_indices: list[int] = []
        self.saved_chunks: list[str] = []
        self.finished = False
        self.aborted = False

    def begin_staged_save(self, *, original_file_url, extracted_text):
        self.original_file_url = original_file_url
        self.extracted_text = extracted_text
        return self.document_id

    def append_staged_chunks(
        self,
        *,
        document_id,
        start_index,
        chunks,
        embeddings_by_provider,
        chunk_metadata=None,
    ):
        self.assert_document_id = document_id
        self.start_indices.append(start_index)
        self.saved_chunks.extend(chunks)
        self.embeddings_by_provider = embeddings_by_provider
        self.chunk_metadata_by_batch = getattr(self, "chunk_metadata_by_batch", [])
        self.chunk_metadata_by_batch.append(chunk_metadata)

    def finish_staged_save(self, document_id, chunk_count):
        self.finished = True
        return SavedDocument(document_id=document_id, chunk_count=chunk_count)

    def abort_staged_save(self, _document_id):
        self.aborted = True


class FakeBatchEmbedder:
    provider = "remote-dual"
    model = "jina-v4 + medical-bgem3"
    dimension = 1024

    def __init__(self) -> None:
        self.batch_sizes: list[int] = []

    async def embed_chunks(self, chunks):
        self.batch_sizes.append(len(chunks))
        return EmbeddingBatch(
            vectors_by_provider={
                "jina-v4": [[0.1] * 1024 for _ in chunks],
                "medical-bgem3": [[0.2] * 1024 for _ in chunks],
            }
        )


if __name__ == "__main__":
    unittest.main()
