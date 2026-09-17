import os
import unittest
from io import BytesIO

from PIL import Image, ImageDraw

from ai.ocr import run_ocr


@unittest.skipUnless(
    os.getenv("RUN_PADDLE_OCR_SMOKE") == "1",
    "RUN_PADDLE_OCR_SMOKE=1일 때만 실제 Paddle Model을 실행합니다.",
)
class PaddleOcrSmokeTest(unittest.TestCase):
    def test_actual_model_initializes_and_returns_contract(self) -> None:
        image = Image.new("RGB", (600, 180), "white")
        ImageDraw.Draw(image).text((40, 60), "OCR SMOKE 123", fill="black")
        output = BytesIO()
        image.save(output, format="PNG")

        result = run_ocr(output.getvalue(), min_confidence=0.0)

        self.assertIsInstance(result.text, str)
        self.assertIsInstance(result.lines, list)


if __name__ == "__main__":
    unittest.main()
