import asyncio
import threading
import unittest
from io import BytesIO

from fastapi import UploadFile
from starlette.datastructures import Headers

from ai.ocr import OcrDocumentResult, OcrLine, OcrProcessingConfig
from ai.ocr.errors import DocumentValidationError
from app.services.ocr_chunk_service import create_chunks
from app.services.ocr_workflow import OcrWorkflowService, build_admin_ocr_response


class OcrWorkflowServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.core_calls = 0
        self.core_thread_id: int | None = None

        def fake_core(document, _config, progress_callback):
            self.core_calls += 1
            self.core_thread_id = threading.get_ident()
            if progress_callback is not None:
                progress_callback("extracting", 80, "공통 Core 추출 완료")
            return OcrDocumentResult(
                raw_text="원문\x00",
                cleaned_text="정제된 OCR 텍스트 " * 20,
                lines=[OcrLine("정제된 OCR 텍스트", 0.95, page=0)],
                page_count=1,
                document_type="image",
                ocr_image_count=1,
                average_confidence=0.95,
                warnings=[],
            )

        self.service = OcrWorkflowService(
            config=OcrProcessingConfig(
                max_file_bytes=1024 * 1024,
                max_pdf_pages=5,
                native_text_min_chars=20,
                significant_image_area_ratio=0.03,
                pdf_render_dpi=100,
                max_image_side=1200,
                max_image_pixels=1_000_000,
                paddle_device="cpu",
                paddle_language="korean",
            ),
            core_analyzer=fake_core,
        )

    def test_upload_analysis_runs_core_outside_event_loop_thread(self) -> None:
        async def scenario() -> None:
            event_loop_thread_id = threading.get_ident()

            result = await self.service.analyze_upload(_upload())

            self.assertEqual(result.raw_text, "원문\x00")
            self.assertNotEqual(self.core_thread_id, event_loop_thread_id)

        asyncio.run(scenario())

    def test_admin_response_adds_chunks_without_changing_core_text(self) -> None:
        progress_values: list[int] = []

        result = asyncio.run(
            self.service.process_document(
                _upload(),
                chunk_size=100,
                overlap=20,
                progress_callback=lambda _stage, progress, _message: progress_values.append(progress),
            )
        )

        self.assertEqual(self.core_calls, 1)
        self.assertEqual(result.extracted_text, "정제된 OCR 텍스트 " * 20)
        self.assertGreater(len(result.chunks), 1)
        self.assertEqual(result.confidence, 95.0)
        self.assertEqual(result.readiness, "ready")
        self.assertEqual(progress_values, sorted(progress_values))

    def test_invalid_overlap_is_rejected_before_core_execution(self) -> None:
        with self.assertRaises(DocumentValidationError):
            asyncio.run(
                self.service.process_document(
                    _upload(),
                    chunk_size=100,
                    overlap=100,
                )
            )
        self.assertEqual(self.core_calls, 0)

    def test_character_chunking_moves_forward_and_keeps_limit(self) -> None:
        text = "문서 처리 흐름을 확인하기 위한 문장입니다. " * 20

        chunks = create_chunks(text, chunk_size=120, overlap=20)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunks))
        self.assertTrue(all(len(chunk) <= 120 for chunk in chunks))

    def test_direct_text_document_has_readable_admin_notes(self) -> None:
        response = build_admin_ocr_response(
            file_name="knowledge.jsonl",
            result=OcrDocumentResult(
                raw_text='{"text": "샘플"}',
                cleaned_text='{"text": "샘플"}',
                lines=[],
                page_count=None,
                document_type="jsonl_direct",
                ocr_image_count=0,
                average_confidence=1.0,
                warnings=[],
            ),
            chunks=['{"text": "샘플"}'],
        )

        self.assertEqual(response.readiness, "ready")
        self.assertEqual(response.confidence, 100.0)
        self.assertIn("원본 형식: JSONL", response.notes)
        self.assertIn("문서 유형: JSONL 직접 추출", response.notes)

    def test_zip_document_has_readable_admin_notes(self) -> None:
        response = build_admin_ocr_response(
            file_name="knowledge.zip",
            result=OcrDocumentResult(
                raw_text="압축 텍스트",
                cleaned_text="압축 텍스트",
                lines=[],
                page_count=None,
                document_type="zip_archive",
                ocr_image_count=0,
                average_confidence=1.0,
                warnings=[],
            ),
            chunks=["압축 텍스트"],
        )

        self.assertIn("원본 형식: ZIP", response.notes)
        self.assertIn("문서 유형: ZIP 압축 문서", response.notes)


def _upload() -> UploadFile:
    return UploadFile(
        file=BytesIO(b"image-content"),
        filename="sample.png",
        headers=Headers({"content-type": "image/png"}),
    )


if __name__ == "__main__":
    unittest.main()
