import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from ai.ocr import OcrDocumentResult, OcrLine
from ai.ocr.errors import DocumentValidationError
from app.api.auth.dependencies import get_current_user
from app.main import app


class DocumentOcrApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="test-user")
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.pop(get_current_user, None)

    def test_response_keeps_text_and_actual_line_contract(self) -> None:
        core_result = OcrDocumentResult(
            raw_text="원문",
            cleaned_text="첫 줄\n둘째 줄",
            lines=[
                OcrLine("첫 줄", 0.95, page=0),
                OcrLine("둘째 줄", 0.88, page=1),
            ],
            page_count=2,
            document_type="scanned_pdf",
            ocr_image_count=2,
            average_confidence=0.915,
            warnings=[],
        )

        with patch(
            "app.api.documents.router.analyze_uploaded_document",
            new=AsyncMock(return_value=core_result),
        ):
            response = self.client.post(
                "/api/documents/ocr",
                files={"file": ("sample.pdf", b"pdf", "application/pdf")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "text": "첫 줄\n둘째 줄",
                "lines": [
                    {"text": "첫 줄", "confidence": 0.95, "page": 0},
                    {"text": "둘째 줄", "confidence": 0.88, "page": 1},
                ],
            },
        )

    def test_domain_validation_error_remains_422(self) -> None:
        with patch(
            "app.api.documents.router.analyze_uploaded_document",
            new=AsyncMock(side_effect=DocumentValidationError("지원하지 않는 문서입니다.")),
        ):
            response = self.client.post(
                "/api/documents/ocr",
                files={"file": ("sample.txt", b"text", "text/plain")},
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "지원하지 않는 문서입니다.")


if __name__ == "__main__":
    unittest.main()
