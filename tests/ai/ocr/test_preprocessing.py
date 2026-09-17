import unittest
from io import BytesIO

import cv2
import numpy as np
from PIL import Image

from ai.ocr.preprocessing import deskew, preprocess_image


class OcrPreprocessingTest(unittest.TestCase):
    def test_exif_orientation_is_applied_before_resize(self) -> None:
        output = BytesIO()
        image = Image.new("RGB", (400, 200), "white")
        exif = Image.Exif()
        exif[274] = 6
        image.save(output, format="JPEG", exif=exif)

        processed = preprocess_image(
            output.getvalue(),
            max_image_side=1200,
            max_image_pixels=1_000_000,
            enable_denoise=False,
            enable_deskew=False,
        )

        self.assertEqual(processed.size, (200, 400))

    def test_transparent_background_is_composed_on_white(self) -> None:
        output = BytesIO()
        Image.new("RGBA", (20, 20), (0, 0, 0, 0)).save(output, format="PNG")

        processed = preprocess_image(
            output.getvalue(),
            enable_denoise=False,
            enable_deskew=False,
        )

        self.assertEqual(processed.mode, "RGB")
        self.assertEqual(processed.getpixel((0, 0)), (255, 255, 255))

    def test_large_image_is_resized_only_to_configured_side(self) -> None:
        output = BytesIO()
        Image.new("RGB", (2000, 1000), "white").save(output, format="PNG")

        processed = preprocess_image(
            output.getvalue(),
            max_image_side=1200,
            max_image_pixels=3_000_000,
            enable_denoise=False,
            enable_deskew=False,
        )

        self.assertEqual(processed.size, (1200, 600))

    def test_horizontal_text_guides_are_not_rotated_vertically(self) -> None:
        image = np.full((200, 600, 3), 255, dtype=np.uint8)
        cv2.line(image, (40, 80), (560, 80), (0, 0, 0), 3)
        cv2.line(image, (40, 130), (560, 130), (0, 0, 0), 3)

        processed = deskew(image)

        self.assertEqual(processed.shape, image.shape)
        self.assertTrue(np.array_equal(processed, image))


if __name__ == "__main__":
    unittest.main()
