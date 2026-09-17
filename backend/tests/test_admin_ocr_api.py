import unittest
from io import BytesIO
from unittest.mock import AsyncMock, patch
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi.testclient import TestClient

from app.main import app
from app.api.auth.dependencies import require_admin
from app.schemas.admin import OcrDocumentResponse, OcrJobCreatedResponse


class AdminOcrApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def setUp(self) -> None:
        # 2026-09-07: analyze/jobs 등도 관리자 인증이 필요해졌다 - 인증 자체를
        # 검증하는 test_*_requires_admin_authentication류를 제외한 나머지는
        # 전부 관리자로 통과했다고 가정하고 그 뒤의 동작만 검증한다.
        app.dependency_overrides[require_admin] = lambda: object()
        self.addCleanup(app.dependency_overrides.pop, require_admin, None)

    def test_analyze_keeps_multipart_aliases_and_response_contract(self) -> None:
        with patch(
            "app.api.admin.router.process_document",
            new=AsyncMock(return_value=_admin_result()),
        ) as processor:
            response = self.client.post(
                "/api/admin/ocr/analyze",
                files={"file": ("sample.png", b"image", "image/png")},
                data={"chunkSize": "300", "overlap": "40"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["documentName"], "sample.png")
        self.assertEqual(response.json()["extractedText"], "본문 텍스트")
        processor.assert_awaited_once()
        self.assertEqual(processor.await_args.kwargs["chunk_size"], 300)
        self.assertEqual(processor.await_args.kwargs["overlap"], 40)

    def test_analyze_accepts_50_character_chunk_size(self) -> None:
        with patch(
            "app.api.admin.router.process_document",
            new=AsyncMock(return_value=_admin_result()),
        ) as processor:
            response = self.client.post(
                "/api/admin/ocr/analyze",
                files={"file": ("sample.png", b"image", "image/png")},
                data={"chunkSize": "50", "overlap": "5"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(processor.await_args.kwargs["chunk_size"], 50)
        self.assertEqual(processor.await_args.kwargs["overlap"], 5)

    def test_analyze_rejects_chunk_size_below_50(self) -> None:
        response = self.client.post(
            "/api/admin/ocr/analyze",
            files={"file": ("sample.png", b"image", "image/png")},
            data={"chunkSize": "49", "overlap": "0"},
        )

        self.assertEqual(response.status_code, 422)

    def test_analyze_accepts_json_for_rag_chunking(self) -> None:
        response = self.client.post(
            "/api/admin/ocr/analyze",
            files={
                "file": (
                    "knowledge.json",
                    '{"symptom": "두통", "guide": "안정을 취하세요"}'.encode(),
                    "application/json",
                )
            },
            data={"chunkSize": "100", "overlap": "10"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["documentName"], "knowledge.json")
        self.assertIn('"symptom": "두통"', payload["extractedText"])
        self.assertEqual(payload["confidence"], 100.0)
        self.assertIn("원본 형식: JSON", payload["notes"])

    def test_analyze_accepts_zip_for_rag_chunking(self) -> None:
        archive_content = BytesIO()
        with ZipFile(archive_content, "w", ZIP_DEFLATED) as archive:
            archive.writestr("guide.txt", "압축 파일의 RAG 텍스트")
            archive.writestr("data.json", '{"department": "내과"}')

        response = self.client.post(
            "/api/admin/ocr/analyze",
            files={
                "file": (
                    "knowledge.zip",
                    archive_content.getvalue(),
                    "application/zip",
                )
            },
            data={"chunkSize": "100", "overlap": "10"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["documentName"], "knowledge.zip")
        self.assertIn("압축 파일의 RAG 텍스트", payload["extractedText"])
        self.assertIn("원본 형식: ZIP", payload["notes"])

    def test_url_job_requires_admin_authentication(self) -> None:
        # setUp이 기본으로 관리자 인증을 통과시켜두므로, 이 테스트만 잠깐 되돌려서
        # 진짜로 인증 없이는 401이 나는지 확인한다.
        app.dependency_overrides.pop(require_admin, None)
        response = self.client.post(
            "/api/admin/ocr/url-jobs",
            json={"url": "https://example.com", "chunkSize": 300, "overlap": 40},
        )
        self.assertEqual(response.status_code, 401)

    def test_url_job_accepts_camel_case_contract_for_admin(self) -> None:
        with patch(
            "app.api.admin.router.ocr_job_manager.create_url_job",
            new=AsyncMock(
                return_value=OcrJobCreatedResponse(jobId="url-job", status="queued")
            ),
        ) as creator:
            response = self.client.post(
                "/api/admin/ocr/url-jobs",
                json={
                    "url": "https://example.com/article",
                    "chunkSize": 300,
                    "overlap": 40,
                },
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"jobId": "url-job", "status": "queued"})
        creator.assert_awaited_once_with("https://example.com/article", 300, 40)


def _admin_result() -> OcrDocumentResponse:
    return OcrDocumentResponse(
        documentName="sample.png",
        pageCount=1,
        characterCount=4,
        estimatedChunks=1,
        confidence=95.0,
        extractedText="본문 텍스트",
        chunks=["본문 텍스트"],
        readiness="ready",
        notes=["문서 유형: 이미지"],
    )


if __name__ == "__main__":
    unittest.main()
