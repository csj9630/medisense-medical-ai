"""이전 Admin OCR 공개 Import를 새 Backend Workflow로 연결하는 호환 Package입니다."""

from app.services.ocr_workflow import process_document

__all__ = ["process_document"]
