import unittest
from typing import Any

from ai.rag.ingestion.adapters.base import DatasetAdapter
from ai.rag.ingestion.pipeline import IngestionSink, run_ingestion_pipeline
from ai.rag.ingestion.schema import NormalizedRecord

_LONG_TEXT = "충수염은 맹장 끝에 달린 충수에 염증이 생기는 질환으로 우측 하복부 통증이 특징입니다. " * 3


class FakeAdapter(DatasetAdapter):
    """실제 HuggingFace 네트워크 호출 없이 pipeline 로직만 검증하기 위한 가짜 어댑터.
    load_raw()를 오버라이드해서 고정된 행 목록을 그대로 돌려준다."""

    source = "FakeSource"
    source_type = "fake"
    hf_path = "fake/dataset"

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def load_raw(self, limit: int | None = None, *, shuffle_seed: int | None = None):  # noqa: ANN201 - 테스트 stub
        rows = self._rows[:limit] if limit is not None else self._rows
        return iter(rows)

    def to_normalized(self, raw_row: dict[str, Any], index: int) -> NormalizedRecord | None:
        content = raw_row.get("content")
        if not content:
            return None
        return NormalizedRecord(
            source=self.source,
            source_type=self.source_type,
            content=content,
            original_id=str(index),
            original_dataset=self.hf_path,
        )


class RunIngestionPipelineTest(unittest.TestCase):
    def test_counts_add_up_for_mixed_valid_short_and_duplicate_rows(self) -> None:
        adapter = FakeAdapter(
            [
                {"content": _LONG_TEXT},  # 정상
                {"content": "짧음"},  # cleaning에서 탈락(너무 짧음)
                {"content": _LONG_TEXT},  # 첫 번째와 내용 동일 -> dedup에서 탈락
                {"content": _LONG_TEXT + " 추가 문장으로 다른 내용을 만듭니다."},  # 정상(다른 내용)
            ]
        )
        result = run_ingestion_pipeline(adapter)

        self.assertEqual(result.raw_count, 4)
        self.assertEqual(result.duplicate_count, 1)
        self.assertEqual(result.documents_count, 2)
        self.assertGreater(result.chunk_count, 0)

    def test_limit_is_forwarded_to_adapter(self) -> None:
        adapter = FakeAdapter([{"content": _LONG_TEXT} for _ in range(10)])
        result = run_ingestion_pipeline(adapter, limit=3)
        self.assertEqual(result.raw_count, 3)

    def test_shuffle_seed_is_forwarded_to_adapter(self) -> None:
        # "앞에서부터 N개"가 아니라 전체에서 고르게 뽑도록(komed-instruct 등 대량
        # 데이터셋 일부만 쓸 때) shuffle_seed가 load_raw까지 그대로 전달돼야 한다.
        received: dict[str, Any] = {}
        adapter = FakeAdapter([{"content": _LONG_TEXT}])
        original_load_raw = adapter.load_raw

        def spying_load_raw(limit=None, *, shuffle_seed=None):
            received["shuffle_seed"] = shuffle_seed
            return original_load_raw(limit, shuffle_seed=shuffle_seed)

        adapter.load_raw = spying_load_raw
        run_ingestion_pipeline(adapter, limit=1, shuffle_seed=42)
        self.assertEqual(received["shuffle_seed"], 42)

    def test_none_normalized_rows_are_skipped_without_error(self) -> None:
        adapter = FakeAdapter([{"content": ""}, {"content": _LONG_TEXT}])
        result = run_ingestion_pipeline(adapter)
        self.assertEqual(result.raw_count, 2)
        self.assertEqual(result.documents_count, 1)

    def test_document_metadata_includes_needs_review_flag(self) -> None:
        dosage_text = ("이 약물의 권장 용량은 하루 500mg이며 " + _LONG_TEXT)
        adapter = FakeAdapter([{"content": dosage_text}])
        result = run_ingestion_pipeline(adapter)
        self.assertEqual(result.documents_count, 1)
        self.assertTrue(result.records[0].document_metadata["needs_review"])

    def test_sink_hooks_fire_for_each_stage_without_changing_result(self) -> None:
        # sink는 순수 관찰자여야 한다 - 넘겨도 안 넘겨도 result는 동일해야 한다.
        adapter = FakeAdapter(
            [
                {"content": _LONG_TEXT},  # 정상 -> raw/normalized/processed/record 전부 호출
                {"content": "짧음"},  # cleaning 탈락 -> raw만 호출
                {"content": _LONG_TEXT},  # dedup 탈락 -> raw/normalized/duplicate 호출
            ]
        )
        raw_calls: list[dict] = []
        normalized_calls: list[NormalizedRecord] = []
        processed_calls: list[NormalizedRecord] = []
        duplicate_calls: list[NormalizedRecord] = []
        record_calls: list = []
        sink = IngestionSink(
            on_raw=raw_calls.append,
            on_normalized=normalized_calls.append,
            on_processed=processed_calls.append,
            on_duplicate=duplicate_calls.append,
            on_record=record_calls.append,
        )

        result_with_sink = run_ingestion_pipeline(adapter, sink=sink)
        result_without_sink = run_ingestion_pipeline(adapter)

        self.assertEqual(result_with_sink.raw_count, result_without_sink.raw_count)
        self.assertEqual(result_with_sink.documents_count, result_without_sink.documents_count)
        self.assertEqual(result_with_sink.duplicate_count, result_without_sink.duplicate_count)
        self.assertEqual(len(raw_calls), 3)
        self.assertEqual(len(normalized_calls), 2)  # 짧은 것 제외 2개가 정제까지 통과
        self.assertEqual(len(processed_calls), 1)  # 그중 중복 아닌 1개만 processed
        self.assertEqual(len(duplicate_calls), 1)
        self.assertEqual(len(record_calls), 1)


if __name__ == "__main__":
    unittest.main()
