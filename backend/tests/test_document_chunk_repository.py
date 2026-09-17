import unittest
from unittest.mock import MagicMock
from uuid import uuid4

from app.repositories.document_chunk import (
    EMBEDDING_COLUMN_WIDTH,
    DocumentChunkRepository,
    pad_embedding,
)


class PadEmbeddingTest(unittest.TestCase):
    def test_column_width_matches_actual_jina_bge_dimension(self) -> None:
        # 실제 확정된 Jina v4/Medical BGE-M3가 둘 다 1024차원이라 컬럼 폭도 1024여야
        # 한다(마이그레이션 a1f3c9d2e8b4로 2048에서 좁힘 - 실제 DB에서 뒤 1024차원이
        # 전부 0-padding이었고 전체 DB 용량의 42%를 차지한 걸 확인하고 결정함).
        self.assertEqual(EMBEDDING_COLUMN_WIDTH, 1024)

    def test_vector_matching_column_width_is_unchanged(self) -> None:
        vector = [0.1] * EMBEDDING_COLUMN_WIDTH
        self.assertEqual(pad_embedding(vector), vector)

    def test_shorter_vector_is_padded_with_zeros(self) -> None:
        result = pad_embedding([0.1, 0.2])
        self.assertEqual(len(result), EMBEDDING_COLUMN_WIDTH)
        self.assertEqual(result[:2], [0.1, 0.2])
        self.assertTrue(all(v == 0.0 for v in result[2:]))

    def test_vector_wider_than_column_raises(self) -> None:
        with self.assertRaises(ValueError):
            pad_embedding([0.1] * (EMBEDDING_COLUMN_WIDTH + 1))


class CreateChunksMetadataTest(unittest.TestCase):
    def test_metadata_is_applied_to_every_chunk(self) -> None:
        db = MagicMock()
        repo = DocumentChunkRepository(db)
        document_id = uuid4()
        metadata = {"source": "Asan-AMC-Healthinfo", "needs_review": False}

        chunks = repo.create_chunks(
            document_id,
            [
                {"chunk_index": 0, "chunk_text": "첫 번째 청크"},
                {"chunk_index": 1, "chunk_text": "두 번째 청크"},
            ],
            metadata=metadata,
        )

        self.assertEqual(len(chunks), 2)
        for chunk in chunks:
            self.assertEqual(chunk.chunk_metadata, metadata)
        db.add_all.assert_called_once()
        db.commit.assert_called_once()

    def test_omitting_metadata_leaves_it_none(self) -> None:
        # 기존 OCR 저장 경로가 metadata를 안 넘기던 대로 계속 동작해야 한다(하위호환).
        db = MagicMock()
        repo = DocumentChunkRepository(db)

        chunks = repo.create_chunks(
            uuid4(), [{"chunk_index": 0, "chunk_text": "청크"}]
        )

        self.assertIsNone(chunks[0].chunk_metadata)

    def test_commit_true_commits_and_refreshes_each_chunk(self) -> None:
        # 기존 단일 문서(OCR) 경로 - commit()과 청크별 refresh() 둘 다 호출돼야 한다.
        db = MagicMock()
        repo = DocumentChunkRepository(db)

        chunks = repo.create_chunks(
            uuid4(),
            [{"chunk_index": 0, "chunk_text": "a"}, {"chunk_index": 1, "chunk_text": "b"}],
            commit=True,
        )

        db.commit.assert_called_once()
        db.flush.assert_not_called()
        self.assertEqual(db.refresh.call_count, 2)

    def test_commit_false_flushes_without_per_chunk_refresh(self) -> None:
        # 대량 ingestion 경로 - flush()만 하고 청크별 refresh() 왕복은 생략해야
        # 한다(실제로 문서 수십 개 처리 시 이 refresh 왕복들이 체감될 만큼 느렸다).
        db = MagicMock()
        repo = DocumentChunkRepository(db)

        repo.create_chunks(
            uuid4(),
            [{"chunk_index": 0, "chunk_text": "a"}, {"chunk_index": 1, "chunk_text": "b"}],
            commit=False,
        )

        db.flush.assert_called_once()
        db.commit.assert_not_called()
        db.refresh.assert_not_called()


if __name__ == "__main__":
    unittest.main()
