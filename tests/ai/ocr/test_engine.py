import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import sleep
from unittest.mock import patch

from PIL import Image

from ai.ocr.engine import PaddleOcrService, parse_predictions
from ai.ocr.errors import OcrUnavailableError


class PaddleResultParsingTest(unittest.TestCase):
    def test_box_order_lines_confidence_and_raw_text_are_preserved(self) -> None:
        predictions = [
            {
                "res": {
                    "rec_texts": ["아래", "위", "낮은 신뢰도"],
                    "rec_scores": [0.9, 0.8, 0.2],
                    "rec_boxes": [
                        [10, 100, 80, 120],
                        [10, 10, 80, 30],
                        [100, 10, 180, 30],
                    ],
                }
            }
        ]

        result = parse_predictions(predictions, min_confidence=0.5)

        self.assertEqual([line.text for line in result.lines], ["위", "낮은 신뢰도", "아래"])
        self.assertEqual(result.raw_text, "위\n낮은 신뢰도\n아래")
        self.assertEqual(result.text, "위\n아래")
        self.assertAlmostEqual(result.confidence, (0.8 + 0.2 + 0.9) / 3)
        self.assertEqual(result.lines[0].box, (10.0, 10.0, 80.0, 30.0))

    def test_pipeline_is_created_lazily_and_cached(self) -> None:
        service = _CountingPaddleService()

        self.assertIsNone(service._pipeline)
        first = service._get_pipeline()
        second = service._get_pipeline()

        self.assertIs(first, second)
        self.assertEqual(service.create_count, 1)

    def test_predict_calls_are_serialized_for_one_pipeline(self) -> None:
        pipeline = _ConcurrentProbePipeline()
        service = PaddleOcrService("cpu", "korean")
        service._pipeline = pipeline
        image = Image.new("RGB", (20, 20), "white")

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(service.extract_text, image) for _ in range(2)]
            for future in futures:
                future.result()

        self.assertEqual(pipeline.maximum_active_calls, 1)

    def test_korean_uses_explicit_lightweight_models_not_heavy_default(self) -> None:
        # lang="korean"만 넘기면 PaddleOCR이 기본으로 무거운 "server" 디텍션 모델을
        # 골라서 메모리를 훨씬 많이 먹는다(실측 15GB+) — 그래서 모델 이름을 전부
        # 명시해야 한다. 이 테스트는 그 회귀를 막는다.
        service = PaddleOcrService("cpu", "korean")

        with patch("paddleocr.PaddleOCR") as mock_paddle_ocr:
            service._create_pipeline()

        _, kwargs = mock_paddle_ocr.call_args
        self.assertNotIn("lang", kwargs)
        self.assertEqual(kwargs["text_detection_model_name"], "PP-OCRv5_mobile_det")
        self.assertEqual(kwargs["text_recognition_model_name"], "korean_PP-OCRv5_mobile_rec")
        self.assertEqual(kwargs["textline_orientation_model_name"], "PP-LCNet_x0_25_textline_ori")

    def test_other_language_falls_back_to_plain_lang_option(self) -> None:
        # 한국어 외 언어는 경량 모델 조합을 검증하지 않았으므로 기존 lang= 방식을 유지한다.
        service = PaddleOcrService("cpu", "en")

        with patch("paddleocr.PaddleOCR") as mock_paddle_ocr:
            service._create_pipeline()

        _, kwargs = mock_paddle_ocr.call_args
        self.assertEqual(kwargs["lang"], "en")
        self.assertNotIn("text_detection_model_name", kwargs)

    def test_initialization_failure_is_logged_with_original_cause(self) -> None:
        cause = RuntimeError("missing OCR dependency")
        service = PaddleOcrService("cpu", "korean")
        with (
            patch("paddleocr.PaddleOCR", side_effect=cause),
            self.assertLogs("ai.ocr.engine", level="ERROR") as logs,
            self.assertRaises(OcrUnavailableError) as raised,
        ):
            service._create_pipeline()

        self.assertIs(raised.exception.__cause__, cause)
        self.assertIn("missing OCR dependency", "\n".join(logs.output))
        self.assertNotIn("missing OCR dependency", str(raised.exception))


class _CountingPaddleService(PaddleOcrService):
    def __init__(self) -> None:
        super().__init__("cpu", "korean")
        self.create_count = 0

    def _create_pipeline(self):
        self.create_count += 1
        return object()


class _ConcurrentProbePipeline:
    def __init__(self) -> None:
        self.active_calls = 0
        self.maximum_active_calls = 0
        self.lock = Lock()

    def predict(self, _image):
        with self.lock:
            self.active_calls += 1
            self.maximum_active_calls = max(
                self.maximum_active_calls,
                self.active_calls,
            )
        sleep(0.03)
        with self.lock:
            self.active_calls -= 1
        return []


if __name__ == "__main__":
    unittest.main()
