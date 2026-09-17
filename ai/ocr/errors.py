"""HTTP 상태 코드와 분리된 OCR Domain 예외를 정의합니다."""


class OcrError(Exception):
    """공통 OCR Core에서 처리 가능한 오류의 부모입니다."""


class DocumentValidationError(OcrError):
    """입력 문서가 검증 기준을 만족하지 않을 때 발생합니다."""


class DocumentTooLargeError(DocumentValidationError):
    """입력 문서가 허용 크기를 초과할 때 발생합니다."""


class DocumentProcessingError(OcrError):
    """검증된 문서의 Text 또는 Image를 추출하지 못했을 때 발생합니다."""


class OfficeExtractionError(DocumentProcessingError):
    """DOCX/PPTX의 OOXML 구조를 직접 추출하지 못했을 때 발생합니다."""


class OcrUnavailableError(OcrError):
    """PaddleOCR 의존성이나 모델을 사용할 수 없을 때 발생합니다."""


class WebUrlValidationError(DocumentValidationError):
    """웹 문서 URL이 형식 또는 네트워크 보안 기준을 위반할 때 발생합니다."""


class WebContentTooLargeError(DocumentTooLargeError):
    """웹페이지나 내부 이미지가 설정된 수집 한도를 넘을 때 발생합니다."""


class WebFetchError(DocumentProcessingError):
    """검증된 웹 리소스를 제한 시간 안에 가져오지 못할 때 발생합니다."""


class WebUnsupportedContentError(DocumentValidationError):
    """웹 URL 응답이 HTML 또는 지원 이미지 형식이 아닐 때 발생합니다."""
