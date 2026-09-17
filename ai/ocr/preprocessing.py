"""모든 OCR Image가 공유하는 방향·투명도·크기·노이즈·기울기 전처리입니다."""

from io import BytesIO

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from .errors import DocumentProcessingError

MAX_DIMENSION = 2200
DEFAULT_MAX_PIXELS = 40_000_000
PDF_MAGIC = b"%PDF"


def is_pdf(data: bytes) -> bool:
    return data[:4] == PDF_MAGIC


def load_image(image_bytes: bytes) -> np.ndarray:
    """기존 Local Lab 호환을 위해 Image Bytes를 BGR NumPy 배열로 읽습니다."""

    array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("이미지를 디코딩하지 못했습니다.")
    return image


def resize_if_too_large(
    image: np.ndarray,
    max_dimension: int = MAX_DIMENSION,
) -> np.ndarray:
    height, width = image.shape[:2]
    longest = max(height, width)
    if longest <= max_dimension:
        return image
    scale = max_dimension / longest
    return cv2.resize(
        image,
        (round(width * scale), round(height * scale)),
        interpolation=cv2.INTER_AREA,
    )


def denoise(image: np.ndarray) -> np.ndarray:
    return cv2.fastNlMeansDenoisingColored(image, None, 6, 6, 7, 21)


def deskew(image: np.ndarray) -> np.ndarray:
    """실제 수평 선분의 중앙값만 사용해 정상 Text의 90도 오회전을 방지합니다."""

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=100,
        minLineLength=max(image.shape[1] // 4, 1),
        maxLineGap=10,
    )
    if lines is None:
        return image

    angles: list[float] = []
    for x1, y1, x2, y2 in lines[:, 0]:
        angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        if abs(angle) < 45:
            angles.append(angle)
    if not angles:
        return image

    skew = float(np.median(angles))
    if abs(skew) < 0.5:
        return image

    height, width = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((width // 2, height // 2), skew, 1.0)
    return cv2.warpAffine(
        image,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def preprocess_image(
    content: bytes | Image.Image,
    max_image_side: int = MAX_DIMENSION,
    max_image_pixels: int = DEFAULT_MAX_PIXELS,
    *,
    enable_denoise: bool = True,
    enable_deskew: bool = True,
) -> Image.Image:
    """Image를 한 번 Decode한 뒤 공통 순서로 보정해 RGB Image를 반환합니다."""

    try:
        source_context = (
            Image.open(BytesIO(content))
            if isinstance(content, bytes)
            else content.copy()
        )
        with source_context as source:
            if source.width * source.height > max_image_pixels:
                raise DocumentProcessingError(
                    "OCR 대상 이미지 해상도가 허용 범위를 초과했습니다."
                )
            source.load()

            # 1. 휴대폰 EXIF 방향을 실제 픽셀 방향에 먼저 반영합니다.
            oriented = ImageOps.exif_transpose(source)

            # 2. 투명 영역이 검은 배경으로 인식되지 않도록 흰색과 합성합니다.
            if oriented.mode in {"RGBA", "LA"} or "transparency" in oriented.info:
                rgba_image = oriented.convert("RGBA")
                white_background = Image.new("RGBA", rgba_image.size, "white")
                white_background.alpha_composite(rgba_image)
                processed = white_background.convert("RGB")
            else:
                processed = oriented.convert("RGB")

            # 3. 큰 Image는 이 지점에서 한 번만 Resize합니다.
            if max(processed.size) > max_image_side:
                processed.thumbnail(
                    (max_image_side, max_image_side),
                    Image.Resampling.LANCZOS,
                )

            # 4. OpenCV 보정은 명시적으로 활성화된 경우 한 번의 왕복 변환으로 적용합니다.
            if enable_denoise or enable_deskew:
                bgr_image = cv2.cvtColor(np.asarray(processed), cv2.COLOR_RGB2BGR)
                if enable_denoise:
                    bgr_image = denoise(bgr_image)
                if enable_deskew:
                    bgr_image = deskew(bgr_image)
                processed = Image.fromarray(
                    cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)
                )

            return processed.copy()
    except DocumentProcessingError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise DocumentProcessingError("OCR용 이미지를 준비하지 못했습니다.") from exc


def preprocess(image_bytes: bytes) -> np.ndarray:
    """기존 보조 호출자를 위해 표준 전처리 결과를 BGR NumPy 배열로 반환합니다."""

    processed = preprocess_image(image_bytes)
    return cv2.cvtColor(np.asarray(processed), cv2.COLOR_RGB2BGR)
