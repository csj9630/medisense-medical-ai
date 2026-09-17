import unittest
from unittest.mock import MagicMock
from uuid import uuid4

from app.services.document_ingestion_service import ingest_document


class FakeProvider:
    def __init__(self, name: str = "fake-provider", dimension: int = 4) -> None:
        self.name = name
        self.dimension = dimension

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * self.dimension for _ in texts]


class IngestDocumentMetadataTest(unittest.TestCase):
    def test_metadata_is_forwarded_to_repository(self) -> None:
        repo = MagicMock()
        # create_chunks가 실제 저장된 chunk 목록을 흉내내도록 최소한의 stub을 만든다.
        saved_chunk = MagicMock(id=uuid4(), chunk_text="충수염은 맹장 끝에 생기는 염증입니다.")
        repo.create_chunks.return_value = [saved_chunk]

        metadata = {"source": "Asan-AMC-Healthinfo", "needs_review": False}
        count = ingest_document(
            repo,
            uuid4(),
            "충수염은 맹장 끝에 생기는 염증입니다.",
            providers=[FakeProvider()],
            metadata=metadata,
        )

        self.assertEqual(count, 1)
        self.assertEqual(repo.create_chunks.call_args.kwargs.get("metadata"), metadata)

    def test_omitting_metadata_passes_none(self) -> None:
        repo = MagicMock()
        saved_chunk = MagicMock(id=uuid4(), chunk_text="충수염은 맹장 끝에 생기는 염증입니다.")
        repo.create_chunks.return_value = [saved_chunk]

        ingest_document(
            repo,
            uuid4(),
            "충수염은 맹장 끝에 생기는 염증입니다.",
            providers=[FakeProvider()],
        )

        self.assertIsNone(repo.create_chunks.call_args.kwargs.get("metadata"))


if __name__ == "__main__":
    unittest.main()
