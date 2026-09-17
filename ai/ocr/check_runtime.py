"""Docker 빌드에서 PaddleX 의존성과 실제 OCR 추론을 검증한다."""

import importlib.metadata
import re


OPENCV_DISTRIBUTIONS = (
    "opencv-python",
    "opencv-python-headless",
    "opencv-contrib-python",
    "opencv-contrib-python-headless",
)


def check_runtime() -> None:
    installed = {}
    for name in OPENCV_DISTRIBUTIONS:
        try:
            installed[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            continue
    if set(installed) != {"opencv-contrib-python"}:
        raise RuntimeError(
            "PaddleX OCR에는 opencv-contrib-python 배포판 하나만 필요합니다. "
            f"설치 상태: {installed}"
        )

    # import cv2만으로는 PaddleX의 배포판 이름 검사를 검증할 수 없다.
    import cv2
    from paddlex.utils.deps import require_extra
    from PIL import Image, ImageDraw, ImageFont

    from .engine import get_paddle_ocr_service

    require_extra("ocr-core", obj_name="OCR")
    image = Image.new("RGB", (900, 240), "white")
    ImageDraw.Draw(image).text(
        (40, 70), "OCR TEST 12345", fill="black", font=ImageFont.load_default(size=40)
    )
    result = get_paddle_ocr_service("cpu", "korean").extract_text(image)
    if "12345" not in re.sub(r"\s+", "", result.text):
        raise RuntimeError("합성 이미지의 기준 문자열 12345를 OCR로 읽지 못했습니다.")
    print(
        f"OCR runtime OK: cv2={cv2.__version__}, "
        f"paddleocr={importlib.metadata.version('paddleocr')}, "
        f"paddlex={importlib.metadata.version('paddlex')}, lines={result.line_count}"
    )


if __name__ == "__main__":
    check_runtime()
