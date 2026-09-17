import tempfile
import unittest
from pathlib import Path

from ai.rag.ingestion.dedup import Deduplicator, content_hash, load_hash_index, save_hash_index
from ai.rag.ingestion.schema import NormalizedRecord


def _record(**overrides) -> NormalizedRecord:
    defaults = dict(
        source="TestSource",
        source_type="test",
        content="동일한 내용입니다",
        original_id="1",
        original_dataset="test/dataset",
    )
    defaults.update(overrides)
    return NormalizedRecord(**defaults)


class ContentHashTest(unittest.TestCase):
    def test_identical_records_produce_identical_hash(self) -> None:
        self.assertEqual(content_hash(_record()), content_hash(_record()))

    def test_different_content_produces_different_hash(self) -> None:
        self.assertNotEqual(
            content_hash(_record(content="A")), content_hash(_record(content="B"))
        )

    def test_different_original_id_alone_produces_the_same_hash(self) -> None:
        # 의도적: 같은 내용이 다른 행(original_id)으로 두 번 실린 경우를 진짜 중복으로
        # 잡아야 하므로, original_id는 해시 기준에서 뺐다. idempotency(재실행 skip)는
        # original_id를 쓰는 별도 메커니즘(합성 URL)이 담당한다.
        self.assertEqual(
            content_hash(_record(original_id="1")), content_hash(_record(original_id="2"))
        )

    def test_different_source_but_same_content_produces_same_hash(self) -> None:
        # 의도적: 서로 다른 데이터셋(예: snuh-clinical-qa, komed-instruct)에 동일한
        # 설명이 실린 경우도 중복으로 잡아야 하므로, source는 해시 기준에서 뺐다.
        self.assertEqual(
            content_hash(_record(source="A")), content_hash(_record(source="B"))
        )


class DeduplicatorTest(unittest.TestCase):
    def test_first_occurrence_is_not_duplicate(self) -> None:
        dedup = Deduplicator()
        self.assertFalse(dedup.is_duplicate(_record()))

    def test_second_identical_occurrence_is_duplicate(self) -> None:
        dedup = Deduplicator()
        dedup.is_duplicate(_record())
        self.assertTrue(dedup.is_duplicate(_record()))

    def test_different_content_records_are_both_not_duplicate(self) -> None:
        dedup = Deduplicator()
        self.assertFalse(dedup.is_duplicate(_record(content="첫 번째 내용")))
        self.assertFalse(dedup.is_duplicate(_record(content="두 번째 내용")))

    def test_same_content_different_original_id_is_still_duplicate(self) -> None:
        # 같은 설명이 서로 다른 행(질문 문구만 다름)으로 두 번 실린 실제 시나리오.
        dedup = Deduplicator()
        self.assertFalse(dedup.is_duplicate(_record(original_id="1")))
        self.assertTrue(dedup.is_duplicate(_record(original_id="2")))

    def test_same_content_different_dataset_is_cross_dataset_duplicate(self) -> None:
        # 데이터셋 간 중복 시나리오 - snuh-clinical-qa를 먼저 처리한 뒤 seed로
        # 넘기면, komed-instruct에 같은 내용이 있어도 잡아야 한다.
        dedup = Deduplicator()
        self.assertFalse(
            dedup.is_duplicate(_record(source="snuh/ClinicalQA", original_dataset="snuh/ClinicalQA"))
        )
        self.assertTrue(
            dedup.is_duplicate(
                _record(source="KoMedInstruct-52k", original_dataset="ChuGyouk/KoMedInstruct-52k")
            )
        )

    def test_seed_makes_previously_processed_content_a_duplicate(self) -> None:
        first = Deduplicator()
        first.is_duplicate(_record())
        second = Deduplicator(seed=first.snapshot())
        self.assertTrue(second.is_duplicate(_record()))


class HashIndexPersistenceTest(unittest.TestCase):
    def test_load_missing_file_returns_empty_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_hash_index(Path(tmp) / "missing.json"), set())

    def test_save_then_load_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.json"
            hashes = {"abc123", "def456"}
            save_hash_index(path, hashes)
            self.assertEqual(load_hash_index(path), hashes)


if __name__ == "__main__":
    unittest.main()
