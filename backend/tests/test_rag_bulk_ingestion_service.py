import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from ai.rag.chunking import Chunk
from ai.rag.ingestion.dedup import Deduplicator
from ai.rag.ingestion.pipeline import IngestionPipelineResult, IngestionRecord
from ai.rag.ingestion.schema import NormalizedRecord
from app.services.rag_bulk_ingestion_service import run_bulk_ingestion


def _fake_pipeline_result(
    n: int = 2, *, document_metadata: dict | None = None, filter_stats: dict | None = None
) -> IngestionPipelineResult:
    records = []
    for i in range(n):
        normalized = NormalizedRecord(
            source="Asan-AMC-Healthinfo",
            source_type="hospital_health_information",
            content=f"내용 {i}",
            original_id=str(i),
            original_dataset="ChuGyouk/Asan-AMC-Healthinfo",
        )
        chunks = [Chunk(index=0, text=f"내용 {i}", token_count=3)]
        metadata = document_metadata if document_metadata is not None else {"source": "Asan-AMC-Healthinfo"}
        records.append(IngestionRecord(normalized, chunks, metadata))
    return IngestionPipelineResult(
        source="Asan-AMC-Healthinfo",
        raw_count=n,
        cleaned_count=n,
        duplicate_count=0,
        chunk_count=n,
        records=records,
        filter_stats=filter_stats or {},
    )


class _FakeProvider:
    """실제 RemoteEmbeddingProvider 대신 쓰는 스텁 - 호출 횟수/받은 텍스트를 기록해서
    "문서당 한 번"이 아니라 "배치당 한 번" 호출되는지 확인하는 데 쓴다."""

    def __init__(self, name: str = "jina-v4", dimension: int = 4) -> None:
        self.name = name
        self.dimension = dimension
        self.calls: list[list[str]] = []

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[0.1] * self.dimension for _ in texts]


def _urls_for(n: int) -> list[str]:
    return [f"hf-dataset://Asan-AMC-Healthinfo/{i}" for i in range(n)]


def _db_that_assigns_ids() -> MagicMock:
    """create()/create_chunks()가 flush 뒤 실제 UUID를 갖도록 흉내내고, 기존
    문서가 하나도 없는 것처럼(find_existing_urls -> 빈 set) 응답한다."""
    db = MagicMock()
    db.scalars.return_value = []  # find_existing_urls: 아직 아무것도 없음
    db.refresh.side_effect = lambda obj: setattr(obj, "id", uuid4())
    return db


class RunBulkIngestionDryRunTest(unittest.TestCase):
    def test_dry_run_makes_no_db_writes(self) -> None:
        db = MagicMock()
        db.scalars.return_value = []  # find_existing_urls: 아직 없음

        with patch(
            "app.services.rag_bulk_ingestion_service.run_ingestion_pipeline",
            return_value=_fake_pipeline_result(2),
        ):
            result = run_bulk_ingestion("asan", db, dry_run=True, providers=[_FakeProvider()])

        self.assertEqual(result.documents_ingested, 0)
        self.assertEqual(result.skipped_existing, 0)
        db.add.assert_not_called()
        db.commit.assert_not_called()

    def test_dry_run_reports_skipped_existing(self) -> None:
        db = MagicMock()
        db.scalars.return_value = _urls_for(2)  # 전부 이미 존재하는 것처럼 흉내

        with patch(
            "app.services.rag_bulk_ingestion_service.run_ingestion_pipeline",
            return_value=_fake_pipeline_result(2),
        ):
            result = run_bulk_ingestion("asan", db, dry_run=True, providers=[_FakeProvider()])

        self.assertEqual(result.skipped_existing, 2)
        self.assertEqual(result.documents_ingested, 0)


class RunBulkIngestionRealRunTest(unittest.TestCase):
    def test_creates_document_and_saves_chunks_and_embeddings(self) -> None:
        db = _db_that_assigns_ids()
        provider = _FakeProvider()

        with patch(
            "app.services.rag_bulk_ingestion_service.run_ingestion_pipeline",
            return_value=_fake_pipeline_result(1),
        ):
            result = run_bulk_ingestion("asan", db, dry_run=False, providers=[provider])

        self.assertEqual(result.documents_ingested, 1)
        self.assertEqual(result.chunks_ingested, 1)
        self.assertEqual(result.failed, 0)
        self.assertEqual(len(provider.calls), 1)  # 배치 1회 호출
        self.assertEqual(provider.calls[0], ["내용 0"])

    def test_multiple_documents_are_embedded_in_a_single_batch_call(self) -> None:
        # 핵심 성능 요구사항 - 문서 5개가 embed_texts를 5번이 아니라 1번(배치)만
        # 호출해야 한다(batch_size가 5보다 크므로 전부 한 배치에 들어감).
        db = _db_that_assigns_ids()
        provider = _FakeProvider()

        with patch(
            "app.services.rag_bulk_ingestion_service.run_ingestion_pipeline",
            return_value=_fake_pipeline_result(5),
        ):
            result = run_bulk_ingestion("asan", db, dry_run=False, batch_size=50, providers=[provider])

        self.assertEqual(result.documents_ingested, 5)
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(len(provider.calls[0]), 5)

    def test_batch_size_splits_into_multiple_embed_calls(self) -> None:
        db = _db_that_assigns_ids()
        provider = _FakeProvider()

        with patch(
            "app.services.rag_bulk_ingestion_service.run_ingestion_pipeline",
            return_value=_fake_pipeline_result(5),
        ):
            result = run_bulk_ingestion("asan", db, dry_run=False, batch_size=2, providers=[provider])

        self.assertEqual(result.documents_ingested, 5)
        # 5개 문서, batch_size=2 -> 배치 3개(2+2+1)
        self.assertEqual(len(provider.calls), 3)
        self.assertEqual([len(c) for c in provider.calls], [2, 2, 1])

    def test_both_providers_are_called_per_batch(self) -> None:
        db = _db_that_assigns_ids()
        jina = _FakeProvider(name="jina-v4")
        bge = _FakeProvider(name="medical-bgem3")

        with patch(
            "app.services.rag_bulk_ingestion_service.run_ingestion_pipeline",
            return_value=_fake_pipeline_result(2),
        ):
            run_bulk_ingestion("asan", db, dry_run=False, providers=[jina, bge])

        self.assertEqual(len(jina.calls), 1)
        self.assertEqual(len(bge.calls), 1)

    def test_batch_failure_marks_all_pending_documents_failed_and_rolls_back(self) -> None:
        db = _db_that_assigns_ids()

        class _FailingProvider(_FakeProvider):
            def embed_texts(self, texts: list[str]) -> list[list[float]]:
                raise RuntimeError("원격 임베딩 서버 실패")

        with patch(
            "app.services.rag_bulk_ingestion_service.run_ingestion_pipeline",
            return_value=_fake_pipeline_result(2),
        ):
            result = run_bulk_ingestion("asan", db, dry_run=False, providers=[_FailingProvider()])

        self.assertEqual(result.failed, 2)
        self.assertEqual(result.documents_ingested, 0)
        db.rollback.assert_called()

    def test_deduplicator_is_forwarded_to_pipeline(self) -> None:
        # 여러 데이터셋에 걸친 중복 제거(scripts/rag_ingest.py가 신뢰도 순으로
        # seed해서 넘김)가 실제 저장 경로에도 그대로 전달되는지 확인.
        db = _db_that_assigns_ids()
        dedup = Deduplicator()

        with patch(
            "app.services.rag_bulk_ingestion_service.run_ingestion_pipeline",
            return_value=_fake_pipeline_result(1),
        ) as mock_pipeline:
            run_bulk_ingestion("asan", db, dry_run=False, deduplicator=dedup, providers=[_FakeProvider()])

        self.assertIs(mock_pipeline.call_args.kwargs.get("deduplicator"), dedup)

    def test_shuffle_seed_is_forwarded_to_pipeline(self) -> None:
        # "앞에서부터 N개"가 아니라 전체에서 고르게 뽑도록(komed-instruct 등) CLI의
        # --shuffle-seed가 파이프라인까지 그대로 전달돼야 한다.
        db = _db_that_assigns_ids()

        with patch(
            "app.services.rag_bulk_ingestion_service.run_ingestion_pipeline",
            return_value=_fake_pipeline_result(1),
        ) as mock_pipeline:
            run_bulk_ingestion("asan", db, dry_run=False, shuffle_seed=42, providers=[_FakeProvider()])

        self.assertEqual(mock_pipeline.call_args.kwargs.get("shuffle_seed"), 42)

    def test_filter_stats_are_surfaced_from_pipeline_result(self) -> None:
        db = _db_that_assigns_ids()
        stats = {"rejected_ai_refusal": 4, "stripped_answer_restatement": 229}

        with patch(
            "app.services.rag_bulk_ingestion_service.run_ingestion_pipeline",
            return_value=_fake_pipeline_result(1, filter_stats=stats),
        ):
            result = run_bulk_ingestion("asan", db, dry_run=False, providers=[_FakeProvider()])

        self.assertEqual(result.filter_stats, stats)

    def test_source_tier_and_verification_status_are_tallied_from_records(self) -> None:
        db = _db_that_assigns_ids()
        metadata = {"source": "KoMedInstruct-52k", "source_tier": 4, "verification_status": "translated_synthetic_unverified"}

        with patch(
            "app.services.rag_bulk_ingestion_service.run_ingestion_pipeline",
            return_value=_fake_pipeline_result(3, document_metadata=metadata),
        ):
            result = run_bulk_ingestion("asan", db, dry_run=False, providers=[_FakeProvider()])

        self.assertEqual(result.source_tier_counts, {"4": 3})
        self.assertEqual(
            result.verification_status_counts, {"translated_synthetic_unverified": 3}
        )

    def test_skips_documents_that_already_exist(self) -> None:
        db = MagicMock()
        db.scalars.return_value = _urls_for(3)  # 전부 이미 존재
        provider = _FakeProvider()

        with patch(
            "app.services.rag_bulk_ingestion_service.run_ingestion_pipeline",
            return_value=_fake_pipeline_result(3),
        ):
            result = run_bulk_ingestion("asan", db, dry_run=False, providers=[provider])

        self.assertEqual(result.skipped_existing, 3)
        self.assertEqual(result.documents_ingested, 0)
        self.assertEqual(provider.calls, [])


class CommittedRecordsTest(unittest.TestCase):
    """committed_records는 scripts/rag_ingest.py가 cross-dataset dedup 인덱스를
    저장할 때 쓰는 유일한 근거다 - 실제로 Neon에 durable하게 존재함이 확인된
    레코드만 여기 담겨야 한다(2026-09-02 버그: 저장 실패한 레코드까지 "봤다"는
    이유로 영구 중복 기록되어 asan/snuh-clinical-qa/health-search-qa가 재실행
    시 전부 0건으로 나왔다)."""

    def test_successfully_committed_records_are_included(self) -> None:
        db = _db_that_assigns_ids()

        with patch(
            "app.services.rag_bulk_ingestion_service.run_ingestion_pipeline",
            return_value=_fake_pipeline_result(2),
        ):
            result = run_bulk_ingestion("asan", db, dry_run=False, providers=[_FakeProvider()])

        self.assertEqual(len(result.committed_records), 2)
        self.assertEqual({r.content for r in result.committed_records}, {"내용 0", "내용 1"})

    def test_failed_batch_records_are_excluded(self) -> None:
        # 임베딩/DB 저장이 실패한 레코드는 committed_records에 들어가면 안 된다 -
        # 실제로 Neon에 저장되지 않았는데 "처리했다"고 기록하면 안 되기 때문.
        db = _db_that_assigns_ids()

        class _FailingProvider(_FakeProvider):
            def embed_texts(self, texts: list[str]) -> list[list[float]]:
                raise RuntimeError("Neon 용량 초과")

        with patch(
            "app.services.rag_bulk_ingestion_service.run_ingestion_pipeline",
            return_value=_fake_pipeline_result(2),
        ):
            result = run_bulk_ingestion("asan", db, dry_run=False, providers=[_FailingProvider()])

        self.assertEqual(result.committed_records, [])
        self.assertEqual(result.failed, 2)

    def test_skipped_existing_records_are_included(self) -> None:
        # 이미 이전 실행에서 Neon에 확인된 것도 committed로 취급해야 한다.
        db = MagicMock()
        db.scalars.return_value = _urls_for(2)

        with patch(
            "app.services.rag_bulk_ingestion_service.run_ingestion_pipeline",
            return_value=_fake_pipeline_result(2),
        ):
            result = run_bulk_ingestion("asan", db, dry_run=False, providers=[_FakeProvider()])

        self.assertEqual(len(result.committed_records), 2)

    def test_dry_run_only_includes_already_existing_records(self) -> None:
        # dry-run은 아무것도 실제로 저장하지 않으므로, 새로 만들 레코드는
        # committed_records에 절대 포함되면 안 된다(이미 존재하던 것만 포함).
        db = MagicMock()
        db.scalars.return_value = _urls_for(1)  # 2개 중 1개만 이미 존재

        with patch(
            "app.services.rag_bulk_ingestion_service.run_ingestion_pipeline",
            return_value=_fake_pipeline_result(2),
        ):
            result = run_bulk_ingestion("asan", db, dry_run=True, providers=[_FakeProvider()])

        self.assertEqual(len(result.committed_records), 1)
        self.assertEqual(result.committed_records[0].content, "내용 0")


if __name__ == "__main__":
    unittest.main()
