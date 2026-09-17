import unittest
from io import BytesIO
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image

from ai.ocr import OcrDocumentInput, OcrLine, OcrProcessingConfig, analyze_document, run_ocr
from ai.ocr.contracts import OcrDocumentResult, OcrEngineResult
from ai.ocr.errors import (
    DocumentTooLargeError,
    DocumentValidationError,
    OfficeExtractionError,
)
from tests.fixtures.ocr.factories import (
    make_digital_pdf as _make_digital_pdf,
    make_encrypted_pdf as _make_encrypted_pdf,
    make_hybrid_pdf as _make_hybrid_pdf,
    make_jpg as _make_jpg,
    make_minimal_unreadable_office_package as _make_minimal_unreadable_office_package,
    make_multi_page_digital_pdf as _make_multi_page_digital_pdf,
    make_office_package as _make_office_package,
    make_png as _make_png,
    make_rotated_jpg as _make_rotated_jpg,
    make_scanned_pdf as _make_scanned_pdf,
)


class FakeOcrEngine:
    """실제 모델 다운로드 없이 PaddleOCR 호출 횟수와 반환 흐름을 검증합니다."""

    def __init__(self, text: str = "가짜 OCR 추출 텍스트") -> None:
        self.text = text
        self.call_count = 0
        self.last_image_size: tuple[int, int] | None = None

    def extract_text(self, image: Image.Image) -> OcrEngineResult:
        self.call_count += 1
        self.last_image_size = image.size
        return OcrEngineResult(
            text=self.text,
            confidence=0.95 if self.text else 0.0,
            line_count=1 if self.text else 0,
            processing_time_seconds=0.01,
            lines=[OcrLine(self.text, 0.95)] if self.text else [],
            raw_text=self.text,
        )


class RawOnlyOcrEngine(FakeOcrEngine):
    """Confidence 필터 아래 Line이 원문과 Line 계약에 남는지 검증합니다."""

    def extract_text(self, image: Image.Image) -> OcrEngineResult:
        self.call_count += 1
        self.last_image_size = image.size
        return OcrEngineResult(
            text="",
            confidence=0.2,
            line_count=1,
            processing_time_seconds=0.01,
            lines=[OcrLine("낮은 신뢰도 원문", 0.2)],
            raw_text="낮은 신뢰도 원문",
        )


class OcrPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.ocr_engine = FakeOcrEngine()
        self.config = OcrProcessingConfig(
            max_file_bytes=5 * 1024 * 1024,
            max_pdf_pages=10,
            native_text_min_chars=20,
            significant_image_area_ratio=0.03,
            pdf_render_dpi=100,
            max_image_side=1200,
            max_image_pixels=10_000_000,
            paddle_device="cpu",
            paddle_language="korean",
            enable_denoise=False,
            enable_deskew=False,
        )

    def test_digital_pdf_uses_native_text_without_ocr(self) -> None:
        pdf = _make_digital_pdf()

        result = self._process(pdf, "digital.pdf", "application/pdf")

        self.assertEqual(self.ocr_engine.call_count, 0)
        self.assertEqual(result.page_count, 1)
        self.assertIn("Native digital PDF text", result.cleaned_text)
        self.assertEqual(result.document_type, "digital_pdf")

    def test_scanned_pdf_renders_page_and_calls_ocr_once(self) -> None:
        pdf = _make_scanned_pdf()

        result = self._process(pdf, "scanned.pdf", "application/pdf")

        self.assertEqual(self.ocr_engine.call_count, 1)
        self.assertIn("가짜 OCR 추출 텍스트", result.cleaned_text)
        self.assertEqual(result.document_type, "scanned_pdf")
        self.assertEqual(result.lines[0].page, 0)

    def test_hybrid_pdf_inserts_image_ocr_after_native_text(self) -> None:
        pdf = _make_hybrid_pdf()

        result = self._process(pdf, "hybrid.pdf", "application/pdf")

        self.assertEqual(self.ocr_engine.call_count, 1)
        self.assertIn("Native text before the embedded image", result.cleaned_text)
        self.assertIn("[이미지 OCR]", result.cleaned_text)
        self.assertEqual(result.document_type, "hybrid_pdf")
        self.assertLess(
            result.cleaned_text.index("Native text before"),
            result.cleaned_text.index("[이미지 OCR]"),
        )
        self.assertLess(
            result.cleaned_text.index("[이미지 OCR]"),
            result.cleaned_text.index("Native text after"),
        )

    def test_hybrid_pdf_keeps_low_confidence_raw_line(self) -> None:
        self.ocr_engine = RawOnlyOcrEngine()

        result = self._process(
            _make_hybrid_pdf(),
            "hybrid.pdf",
            "application/pdf",
        )

        self.assertIn("낮은 신뢰도 원문", result.raw_text)
        self.assertNotIn("낮은 신뢰도 원문", result.cleaned_text)
        self.assertEqual(result.lines[0].text, "낮은 신뢰도 원문")

    def test_png_calls_ocr_once(self) -> None:
        image = _make_png()

        result = self._process(image, "sample.png", "image/png")

        self.assertEqual(self.ocr_engine.call_count, 1)
        self.assertEqual(result.page_count, 1)
        self.assertEqual(result.average_confidence, 0.95)
        self.assertEqual(result.lines[0].text, "가짜 OCR 추출 텍스트")

    def test_jpg_is_supported(self) -> None:
        result = self._process(_make_jpg(), "sample.jpg", "image/jpeg")

        self.assertEqual(self.ocr_engine.call_count, 1)
        self.assertIn("가짜 OCR 추출 텍스트", result.cleaned_text)

    def test_docx_extracts_heading_paragraph_and_table_without_ocr(self) -> None:
        result = self._process(
            _make_office_package("docx"),
            "sample.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        self.assertEqual(self.ocr_engine.call_count, 0)
        self.assertIn("DOCX direct extraction heading", result.cleaned_text)
        self.assertIn("DOCX paragraph for RAG extraction", result.cleaned_text)
        self.assertIn("| Field | Value |", result.cleaned_text)
        self.assertIsNone(result.page_count)
        self.assertEqual(result.document_type, "docx_direct")
        self.assertTrue(any("실제 페이지 수" in warning for warning in result.warnings))

    def test_pptx_extracts_slide_text_and_notes_without_ocr(self) -> None:
        result = self._process(
            _make_office_package("pptx"),
            "slides.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )

        self.assertEqual(self.ocr_engine.call_count, 0)
        self.assertEqual(result.page_count, 1)
        self.assertIn("PPTX direct extraction title", result.cleaned_text)
        self.assertIn("PPTX speaker notes", result.cleaned_text)
        self.assertEqual(result.document_type, "pptx_direct")

    def test_docx_embedded_image_is_sent_to_ocr(self) -> None:
        result = self._process(
            _make_office_package("docx", include_image=True),
            "image.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        self.assertEqual(self.ocr_engine.call_count, 1)
        self.assertIn("### 이미지 OCR 1", result.cleaned_text)
        self.assertIn("가짜 OCR 추출 텍스트", result.cleaned_text)

    def test_docx_keeps_low_confidence_raw_line(self) -> None:
        self.ocr_engine = RawOnlyOcrEngine()

        result = self._process(
            _make_office_package("docx", include_image=True),
            "image.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        self.assertIn("낮은 신뢰도 원문", result.raw_text)
        self.assertNotIn("낮은 신뢰도 원문", result.cleaned_text)
        self.assertEqual(result.lines[0].text, "낮은 신뢰도 원문")

    def test_pptx_embedded_image_is_sent_to_ocr(self) -> None:
        result = self._process(
            _make_office_package("pptx", include_image=True),
            "image.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )

        self.assertEqual(self.ocr_engine.call_count, 1)
        self.assertIn("가짜 OCR 추출 텍스트", result.cleaned_text)

    def test_text_based_rag_files_are_extracted_without_ocr(self) -> None:
        cases = [
            (
                "data.json",
                "application/json",
                '{"name": "홍길동", "condition": "두통"}'.encode(),
                "json_direct",
                '"condition": "두통"',
            ),
            (
                "data.jsonl",
                "application/x-ndjson",
                '{"question": "배가 아파요"}\n{"answer": "진료가 필요합니다"}\n'.encode(),
                "jsonl_direct",
                "진료가 필요합니다",
            ),
            (
                "data.csv",
                "text/csv",
                "질문,답변\n배가 아파요,진료가 필요합니다\n".encode(),
                "csv_direct",
                "배가 아파요,진료가 필요합니다",
            ),
            (
                "notes.txt",
                "text/plain",
                "RAG에 저장할 일반 텍스트".encode(),
                "txt_direct",
                "RAG에 저장할 일반 텍스트",
            ),
        ]

        for file_name, content_type, content, document_type, expected_text in cases:
            with self.subTest(file_name=file_name):
                result = self._process(content, file_name, content_type)
                self.assertEqual(result.document_type, document_type)
                self.assertIn(expected_text, result.cleaned_text)
                self.assertIsNone(result.page_count)
                self.assertEqual(result.ocr_image_count, 0)
                self.assertEqual(result.average_confidence, 1.0)

        self.assertEqual(self.ocr_engine.call_count, 0)

    def test_zip_combines_supported_members_without_disk_extraction(self) -> None:
        result = self._process(
            _make_zip(
                {
                    "notes/guide.txt": "두통이 있으면 안정을 취하세요.",
                    "data.json": '{"department": "신경과"}',
                    "ignored.gif": b"GIF89a",
                }
            ),
            "knowledge.zip",
            "application/zip",
        )

        self.assertEqual(result.document_type, "zip_archive")
        self.assertIn("## ZIP 내부 파일: notes/guide.txt", result.cleaned_text)
        self.assertIn("두통이 있으면 안정을 취하세요.", result.cleaned_text)
        self.assertIn('"department": "신경과"', result.cleaned_text)
        self.assertTrue(any("건너뛰" in warning for warning in result.warnings))
        self.assertEqual(result.average_confidence, 1.0)
        self.assertEqual(self.ocr_engine.call_count, 0)

    def test_large_image_is_resized_before_ocr(self) -> None:
        image = _make_png(width=2000, height=1000)

        self._process(image, "large.png", "image/png")

        self.assertEqual(self.ocr_engine.last_image_size, (1200, 600))

    def test_exif_orientation_is_applied_before_ocr(self) -> None:
        image = _make_rotated_jpg()

        self._process(image, "rotated.jpg", "image/jpeg")

        self.assertEqual(self.ocr_engine.last_image_size, (200, 400))

    def test_multi_page_digital_pdf_keeps_page_order(self) -> None:
        pdf = _make_multi_page_digital_pdf()

        result = self._process(pdf, "multi.pdf", "application/pdf")

        self.assertEqual(self.ocr_engine.call_count, 0)
        self.assertEqual(result.page_count, 2)
        self.assertLess(
            result.cleaned_text.index("First page native text"),
            result.cleaned_text.index("Second page native text"),
        )

    def test_empty_ocr_result_requires_review(self) -> None:
        self.ocr_engine.text = ""

        result = self._process(_make_scanned_pdf(), "empty.pdf", "application/pdf")

        self.assertEqual(result.cleaned_text, "")
        self.assertEqual(result.average_confidence, 0.0)
        self.assertTrue(result.warnings)

    def test_rejects_corrupted_pdf(self) -> None:
        with self.assertRaises(DocumentValidationError):
            self._process(b"%PDF-corrupted", "broken.pdf", "application/pdf")

    def test_rejects_encrypted_pdf(self) -> None:
        with self.assertRaises(DocumentValidationError):
            self._process(_make_encrypted_pdf(), "locked.pdf", "application/pdf")

    def test_rejects_corrupted_image(self) -> None:
        with self.assertRaises(DocumentValidationError):
            self._process(b"not-an-image", "broken.png", "image/png")

    def test_rejects_wrong_mime_type(self) -> None:
        with self.assertRaises(DocumentValidationError):
            self._process(_make_png(), "sample.png", "text/plain")

    def test_rejects_file_over_size_limit(self) -> None:
        small_config = OcrProcessingConfig(
            **{
                **self.config.__dict__,
                "max_file_bytes": 10,
            }
        )

        with self.assertRaises(DocumentTooLargeError):
            analyze_document(
                OcrDocumentInput("large.png", "image/png", _make_png()),
                small_config,
                ocr_service_factory=lambda: self.ocr_engine,
            )

    def test_rejects_extension_and_binary_mismatch(self) -> None:
        with self.assertRaises(DocumentValidationError):
            self._process(_make_png(), "not-really.pdf", "application/pdf")

    def test_rejects_corrupted_office_archive(self) -> None:
        with self.assertRaises(DocumentValidationError):
            self._process(
                b"PK-not-a-valid-archive",
                "broken.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

    def test_rejects_docx_renamed_as_pptx(self) -> None:
        with self.assertRaises(DocumentValidationError):
            self._process(
                _make_office_package("docx"),
                "renamed.pptx",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )

    def test_rejects_wrong_office_mime_type(self) -> None:
        with self.assertRaises(DocumentValidationError):
            self._process(
                _make_office_package("docx"),
                "sample.docx",
                "text/plain",
            )

    def test_run_ocr_public_wrapper_uses_common_analyzer(self) -> None:
        common_result = OcrDocumentResult(
            raw_text="원문",
            cleaned_text="호환 결과",
            lines=[OcrLine("호환 결과", 0.9)],
            page_count=1,
            document_type="image",
            ocr_image_count=1,
            average_confidence=0.9,
            warnings=[],
        )

        with patch("ai.ocr.pipeline.analyze_document", return_value=common_result) as analyzer:
            result = run_ocr(_make_png(), min_confidence=0.7)

        self.assertEqual(result.text, "호환 결과")
        self.assertEqual(result.min_confidence, 0.7)
        analyzer.assert_called_once()

    def test_valid_zip_with_unreadable_docx_structure_raises_domain_error(self) -> None:
        with self.assertRaises(OfficeExtractionError):
            self._process(
                _make_minimal_unreadable_office_package("docx"),
                "unreadable.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

    def _process(
        self,
        content: bytes,
        file_name: str,
        content_type: str,
    ):
        return analyze_document(
            OcrDocumentInput(file_name, content_type, content),
            self.config,
            ocr_service_factory=lambda: self.ocr_engine,
        )


def _make_zip(files: dict[str, bytes | str]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


if __name__ == "__main__":
    unittest.main()
