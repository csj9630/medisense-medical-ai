import unittest

from ai.ocr.contracts import OcrLine
from ai.ocr.postprocessing import clean_document_text, postprocess


class OcrPostprocessingTest(unittest.TestCase):
    def test_raw_and_cleaned_text_can_remain_separate(self) -> None:
        raw_text = "첫 줄\x00  \n\n\n둘째 줄"

        cleaned = clean_document_text(raw_text)

        self.assertEqual(raw_text, "첫 줄\x00  \n\n\n둘째 줄")
        self.assertEqual(cleaned, "첫 줄\n\n둘째 줄")

    def test_confidence_and_consecutive_duplicate_policy(self) -> None:
        lines = [
            OcrLine("유지", 0.9),
            OcrLine("유지", 0.8),
            OcrLine("제외", 0.49),
            OcrLine("다음", 0.5),
        ]

        self.assertEqual(postprocess(lines, min_confidence=0.5), "유지\n다음")

    def test_same_text_on_different_pages_is_not_deduplicated(self) -> None:
        lines = [OcrLine("본문", 0.9, page=0), OcrLine("본문", 0.9, page=1)]

        result = postprocess(lines)

        self.assertIn("--- 페이지 1 ---", result)
        self.assertIn("--- 페이지 2 ---", result)


if __name__ == "__main__":
    unittest.main()
