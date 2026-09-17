import unittest
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image

from ai.ocr.contracts import OcrDocumentInput, OcrProcessingConfig
from ai.ocr.errors import DocumentTooLargeError, DocumentValidationError
from ai.ocr.validation import validate_document


class OcrValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = OcrProcessingConfig(
            max_file_bytes=1024 * 1024,
            max_pdf_pages=5,
            native_text_min_chars=20,
            significant_image_area_ratio=0.03,
            pdf_render_dpi=100,
            max_image_side=1200,
            max_image_pixels=1_000_000,
            paddle_device="cpu",
            paddle_language="korean",
        )

    def test_valid_png_returns_framework_independent_document(self) -> None:
        validated = validate_document(
            OcrDocumentInput("sample.png", "image/png", _make_png()),
            self.config,
        )

        self.assertEqual(validated.file_type, "image")
        self.assertEqual(validated.file_name, "sample.png")

    def test_empty_file_is_rejected(self) -> None:
        with self.assertRaises(DocumentValidationError):
            validate_document(
                OcrDocumentInput("empty.png", "image/png", b""),
                self.config,
            )

    def test_file_over_limit_is_rejected(self) -> None:
        tiny_config = OcrProcessingConfig(
            **{**self.config.__dict__, "max_file_bytes": 10}
        )
        with self.assertRaises(DocumentTooLargeError):
            validate_document(
                OcrDocumentInput("large.png", "image/png", _make_png()),
                tiny_config,
            )

    def test_extension_binary_mismatch_is_rejected(self) -> None:
        with self.assertRaises(DocumentValidationError):
            validate_document(
                OcrDocumentInput("image.pdf", "application/pdf", _make_png()),
                self.config,
            )

    def test_office_path_traversal_is_rejected(self) -> None:
        output = BytesIO()
        with ZipFile(output, "w", ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", "types")
            archive.writestr("_rels/.rels", "rels")
            archive.writestr("word/document.xml", "document")
            archive.writestr("../outside.txt", "unsafe")

        with self.assertRaises(DocumentValidationError):
            validate_document(
                OcrDocumentInput(
                    "unsafe.docx",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    output.getvalue(),
                ),
                self.config,
            )

    def test_text_based_rag_extensions_are_accepted(self) -> None:
        cases = [
            ("data.json", "application/json", b'{"title": "sample"}', "json"),
            ("data.jsonl", "application/x-ndjson", b'{"id": 1}\n', "jsonl"),
            ("data.csv", "text/csv", b"name,value\nsample,1\n", "csv"),
            ("data.txt", "text/plain", "텍스트 문서".encode(), "txt"),
        ]

        for file_name, content_type, content, expected_type in cases:
            with self.subTest(file_name=file_name):
                validated = validate_document(
                    OcrDocumentInput(file_name, content_type, content),
                    self.config,
                )
                self.assertEqual(validated.file_type, expected_type)

    def test_invalid_json_is_rejected(self) -> None:
        with self.assertRaisesRegex(DocumentValidationError, "JSON 문법"):
            validate_document(
                OcrDocumentInput("broken.json", "application/json", b'{"missing": }'),
                self.config,
            )

    def test_invalid_jsonl_reports_line_number(self) -> None:
        with self.assertRaisesRegex(DocumentValidationError, "2번 줄"):
            validate_document(
                OcrDocumentInput(
                    "broken.jsonl",
                    "application/x-ndjson",
                    b'{"id": 1}\nnot-json\n',
                ),
                self.config,
            )

    def test_zip_with_supported_documents_is_accepted(self) -> None:
        validated = validate_document(
            OcrDocumentInput(
                "knowledge.zip",
                "application/zip",
                _make_zip({"nested/notes.txt": "RAG 문서"}),
            ),
            self.config,
        )

        self.assertEqual(validated.file_type, "zip")

    def test_zip_path_traversal_is_rejected(self) -> None:
        with self.assertRaisesRegex(DocumentValidationError, "안전하지 않은"):
            validate_document(
                OcrDocumentInput(
                    "unsafe.zip",
                    "application/zip",
                    _make_zip({"../outside.txt": "unsafe"}),
                ),
                self.config,
            )

    def test_zip_without_supported_documents_is_rejected(self) -> None:
        with self.assertRaisesRegex(DocumentValidationError, "지원하는 문서"):
            validate_document(
                OcrDocumentInput(
                    "empty.zip",
                    "application/zip",
                    _make_zip({"image.gif": b"GIF89a"}),
                ),
                self.config,
            )

    def test_zip_uncompressed_size_limit_is_enforced(self) -> None:
        tiny_archive_config = OcrProcessingConfig(
            **{
                **self.config.__dict__,
                "max_office_uncompressed_bytes": 10,
            }
        )

        with self.assertRaisesRegex(DocumentValidationError, "압축 해제 크기"):
            validate_document(
                OcrDocumentInput(
                    "large.zip",
                    "application/zip",
                    _make_zip({"large.txt": "x" * 11}),
                ),
                tiny_archive_config,
            )


def _make_png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (100, 60), "white").save(output, format="PNG")
    return output.getvalue()


def _make_zip(files: dict[str, bytes | str]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


if __name__ == "__main__":
    unittest.main()
