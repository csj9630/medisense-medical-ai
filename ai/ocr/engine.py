"""단일 PaddleOCR 모델의 지연 초기화, 동시성 제한과 Line 변환을 담당합니다."""

import logging
from functools import lru_cache
from threading import Lock
from time import perf_counter
from typing import Any

import numpy as np
from PIL import Image

from .contracts import OcrEngineResult, OcrLine
from .errors import DocumentProcessingError, OcrUnavailableError
from .postprocessing import postprocess

logger = logging.getLogger(__name__)


class PaddleOcrService:
    """설정이 같은 요청이 한 Paddle Pipeline을 안전하게 재사용하게 합니다."""

    def __init__(
        self,
        device: str,
        language: str,
        min_confidence: float = 0.5,
    ) -> None:
        self.device = device
        self.language = language
        self.min_confidence = min_confidence
        self._pipeline: Any | None = None
        self._initialization_lock = Lock()
        self._inference_lock = Lock()

    def extract_text(self, image: Image.Image) -> OcrEngineResult:
        pipeline = self._get_pipeline()
        started_at = perf_counter()

        try:
            # Paddle Pipeline은 동시 predict 안전성을 보장하지 않으므로 직렬화합니다.
            with self._inference_lock:
                predictions = pipeline.predict(np.asarray(image))
            parsed = parse_predictions(
                predictions,
                min_confidence=self.min_confidence,
            )
        except OcrUnavailableError:
            raise
        except Exception as exc:
            logger.exception("PaddleOCR 실행 중 오류가 발생했습니다.")
            raise DocumentProcessingError(
                "PaddleOCR 텍스트 추출에 실패했습니다."
            ) from exc

        return OcrEngineResult(
            text=parsed.text,
            confidence=parsed.confidence,
            line_count=parsed.line_count,
            processing_time_seconds=round(perf_counter() - started_at, 3),
            lines=parsed.lines,
            raw_text=parsed.raw_text,
        )

    def _get_pipeline(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline

        with self._initialization_lock:
            if self._pipeline is None:
                self._pipeline = self._create_pipeline()
        return self._pipeline

    def _create_pipeline(self) -> Any:
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise OcrUnavailableError(
                "PaddleOCR가 설치되지 않아 이미지 문서를 분석할 수 없습니다."
            ) from exc

        # 설치 기준인 PaddleOCR 3.7 / PP-OCRv5 옵션을 한곳에서만 관리합니다.
        options = {
            "ocr_version": "PP-OCRv5",
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
            "enable_mkldnn": False,
        }

        if self.language == "korean":
            # 모델 이름을 명시하지 않고 lang="korean"만 쓰면 디텍션이 기본으로
            # "server"(무거운) 버전을 골라서 메모리를 훨씬 많이 먹는다(실측 15GB+까지
            # 올라감). 모델 이름을 하나라도 지정하면 PaddleOCR이 lang= 옵션 전체를
            # 무시하므로, 한국어 인식 모델(korean_PP-OCRv5_mobile_rec)도 반드시 같이
            # 명시해야 한다 — 안 그러면 조용히 일반(비한국어) 인식 모델로 바뀐다.
            options.update(
                {
                    "text_detection_model_name": "PP-OCRv5_mobile_det",
                    "text_recognition_model_name": "korean_PP-OCRv5_mobile_rec",
                    "textline_orientation_model_name": "PP-LCNet_x0_25_textline_ori",
                }
            )
        else:
            # 한국어 외 언어는 아직 경량 모델 조합을 검증하지 않았다 — 기존처럼
            # lang=만 넘겨서 PaddleOCR 기본 동작에 맡긴다.
            options["lang"] = self.language

        try:
            logger.info("PaddleOCR 초기화 시작: device=%s", self.device)
            return PaddleOCR(device=self.device, **options)
        except Exception as first_error:
            logger.exception("PaddleOCR 모델 초기화 실패: device=%s", self.device)
            if self.device.lower() == "cpu":
                raise OcrUnavailableError(
                    "PaddleOCR 모델을 초기화하지 못했습니다."
                ) from first_error

            logger.warning("PaddleOCR GPU 초기화 실패, CPU로 재시도합니다.")
            try:
                return PaddleOCR(device="cpu", **options)
            except Exception as cpu_error:
                logger.exception("PaddleOCR CPU 대체 초기화 실패")
                raise OcrUnavailableError(
                    "PaddleOCR 모델을 GPU와 CPU 모두에서 초기화하지 못했습니다."
                ) from cpu_error


def parse_predictions(
    predictions: Any,
    *,
    min_confidence: float = 0.5,
) -> OcrEngineResult:
    """Paddle 결과를 Box 읽기 순서의 실제 OCR Line과 Text로 변환합니다."""

    lines: list[OcrLine] = []
    for prediction in predictions or []:
        payload = getattr(prediction, "json", prediction)
        if callable(payload):
            payload = payload()
        if not isinstance(payload, dict):
            continue

        result = payload.get("res", payload)
        texts = list(result.get("rec_texts", []))
        scores = list(result.get("rec_scores", []))
        boxes = list(result.get("rec_boxes", []))

        for index, raw_text in enumerate(texts):
            text = str(raw_text).strip()
            if not text:
                continue
            score = float(scores[index]) if index < len(scores) else 0.0
            box = _box_as_tuple(boxes[index]) if index < len(boxes) else None
            lines.append(
                OcrLine(
                    text=text,
                    confidence=score,
                    page=0,
                    box=box,
                    source="ocr",
                )
            )

    lines.sort(key=_line_sort_key)
    raw_text = "\n".join(line.text for line in lines)
    filtered_text = postprocess(lines, min_confidence=min_confidence)
    confidence = (
        sum(line.confidence for line in lines) / len(lines)
        if lines
        else 0.0
    )
    return OcrEngineResult(
        text=filtered_text,
        confidence=confidence,
        line_count=len(lines),
        processing_time_seconds=0.0,
        lines=lines,
        raw_text=raw_text,
    )


def _line_sort_key(line: OcrLine) -> tuple[float, float]:
    if line.box is None or len(line.box) < 2:
        return (float(line.page), 0.0)
    return (float(line.box[1]), float(line.box[0]))


def _box_as_tuple(box: Any) -> tuple[float, ...] | None:
    values = box.tolist() if hasattr(box, "tolist") else list(box)
    flattened = np.asarray(values, dtype=float).reshape(-1).tolist()
    if len(flattened) < 4:
        return None
    return tuple(float(value) for value in flattened)


@lru_cache(maxsize=4)
def get_paddle_ocr_service(
    device: str,
    language: str,
    min_confidence: float = 0.5,
) -> PaddleOcrService:
    """설정이 같은 요청끼리 모델 인스턴스를 재사용합니다."""

    return PaddleOcrService(
        device=device,
        language=language,
        min_confidence=min_confidence,
    )
