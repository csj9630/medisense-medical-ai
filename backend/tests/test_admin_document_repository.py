import unittest
from unittest.mock import MagicMock

from app.repositories.admin_document import AdminDocumentRepository


class FindByOriginalFileUrlTest(unittest.TestCase):
    def test_returns_none_when_absent(self) -> None:
        db = MagicMock()
        db.scalar.return_value = None
        repo = AdminDocumentRepository(db)

        result = repo.find_by_original_file_url("hf-dataset://Asan-AMC-Healthinfo/0")

        self.assertIsNone(result)

    def test_returns_existing_row(self) -> None:
        db = MagicMock()
        existing = MagicMock()
        db.scalar.return_value = existing
        repo = AdminDocumentRepository(db)

        result = repo.find_by_original_file_url("hf-dataset://Asan-AMC-Healthinfo/0")

        self.assertIs(result, existing)


class FindExistingUrlsTest(unittest.TestCase):
    def test_empty_input_returns_empty_set_without_querying(self) -> None:
        db = MagicMock()
        repo = AdminDocumentRepository(db)

        result = repo.find_existing_urls([])

        self.assertEqual(result, set())
        db.scalars.assert_not_called()

    def test_returns_only_the_urls_that_exist(self) -> None:
        # 대량 ingestion에서 레코드마다 SELECT 한 번씩(find_by_original_file_url)
        # 부르면 문서 수천~수만 개일 때 그 자체가 병목이 된다 - IN 쿼리 한 번으로
        # 묶어서 확인한다.
        db = MagicMock()
        db.scalars.return_value = ["hf-dataset://asan/1", "hf-dataset://asan/3"]
        repo = AdminDocumentRepository(db)

        result = repo.find_existing_urls(
            ["hf-dataset://asan/1", "hf-dataset://asan/2", "hf-dataset://asan/3"]
        )

        self.assertEqual(result, {"hf-dataset://asan/1", "hf-dataset://asan/3"})


class CreateTest(unittest.TestCase):
    def test_sets_dataset_import_status(self) -> None:
        db = MagicMock()
        repo = AdminDocumentRepository(db)

        doc = repo.create(
            original_file_url="hf-dataset://Asan-AMC-Healthinfo/0",
            extracted_text="내용",
        )

        self.assertEqual(doc.ocr_status, "dataset_import")
        self.assertEqual(doc.original_file_url, "hf-dataset://Asan-AMC-Healthinfo/0")
        db.commit.assert_called_once()
        db.refresh.assert_called_once()

    def test_commit_false_flushes_without_refresh(self) -> None:
        # 대량 ingestion 경로 - flush()만 하고 refresh() 왕복은 생략해야 한다.
        db = MagicMock()
        repo = AdminDocumentRepository(db)

        repo.create(
            original_file_url="hf-dataset://Asan-AMC-Healthinfo/0",
            extracted_text="내용",
            commit=False,
        )

        db.flush.assert_called_once()
        db.commit.assert_not_called()
        db.refresh.assert_not_called()


if __name__ == "__main__":
    unittest.main()
