import unittest

from ai.rag.ingestion.schema import NormalizedRecord


class NormalizedRecordTest(unittest.TestCase):
    def test_list_fields_default_to_empty_list_not_none(self) -> None:
        record = NormalizedRecord(
            source="S", source_type="T", content="내용", original_id="1", original_dataset="d/s"
        )
        self.assertEqual(record.department, [])
        self.assertEqual(record.disease, [])
        self.assertEqual(record.symptoms, [])
        self.assertEqual(record.metadata, {})

    def test_rejects_empty_original_id(self) -> None:
        with self.assertRaises(ValueError):
            NormalizedRecord(
                source="S", source_type="T", content="내용", original_id="", original_dataset="d/s"
            )

    def test_rejects_empty_original_dataset(self) -> None:
        with self.assertRaises(ValueError):
            NormalizedRecord(
                source="S", source_type="T", content="내용", original_id="1", original_dataset=""
            )

    def test_two_instances_do_not_share_default_list(self) -> None:
        # dataclass의 mutable default 함정 확인 — field(default_factory=list)가
        # 인스턴스마다 독립적인 리스트를 만드는지.
        a = NormalizedRecord(source="S", source_type="T", content="A", original_id="1", original_dataset="d")
        b = NormalizedRecord(source="S", source_type="T", content="B", original_id="2", original_dataset="d")
        object.__setattr__(a, "department", a.department + ["내과"])
        self.assertEqual(b.department, [])


if __name__ == "__main__":
    unittest.main()
