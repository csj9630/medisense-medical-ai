import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.admin.upload_router import register_upload_error_handlers, router
from app.api.auth.dependencies import require_admin
from app.services.large_upload_service import LargeUploadValidationError
from app.services.r2_storage import R2StorageError


class AdminLargeUploadApiTest(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()
        app.include_router(router, prefix="/api/admin")
        app.dependency_overrides[require_admin] = lambda: SimpleNamespace(is_admin=True)
        # 실제 main.py의 create_app()도 이 함수를 불러야 아래 4개 엔드포인트가
        # LargeUploadValidationError/R2StorageError를 422/503으로 바꿔준다 - 테스트도
        # 같은 걸 등록해야 실제 배선과 같은 조건에서 검증된다.
        register_upload_error_handlers(app)
        self.client = TestClient(app)

    def test_init_response_uses_camel_case_contract(self) -> None:
        result = {
            "uploadId": "upload-id",
            "objectKey": "admin-rag-uploads/id/data.txt",
            "partSize": 64 * 1024**2,
            "partCount": 2,
        }
        with patch(
            "app.api.admin.upload_router.large_upload_service.initiate",
            return_value=result,
        ):
            response = self.client.post(
                "/api/admin/ocr/uploads/init",
                json={"fileName": "data.txt", "fileSize": 70 * 1024**2, "contentType": "text/plain"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), result)

    def test_request_over_eight_gib_is_rejected_by_schema(self) -> None:
        response = self.client.post(
            "/api/admin/ocr/uploads/init",
            json={"fileName": "data.txt", "fileSize": 8 * 1024**3 + 1, "contentType": "text/plain"},
        )
        self.assertEqual(response.status_code, 422)

    def test_completed_upload_can_start_remote_job(self) -> None:
        with patch(
            "app.api.admin.upload_router.ocr_job_manager.create_remote_job",
            new=AsyncMock(return_value={"jobId": "job-id", "status": "queued"}),
        ):
            response = self.client.post(
                "/api/admin/ocr/jobs/remote",
                json={
                    "objectKey": "admin-rag-uploads/id/data.txt",
                    "fileName": "data.txt",
                    "fileSize": 100,
                    "contentType": "text/plain",
                    "chunkSize": 512,
                    "overlap": 50,
                },
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"jobId": "job-id", "status": "queued"})

    def test_validation_error_is_translated_to_422_on_every_upload_endpoint(self) -> None:
        # 4개 엔드포인트 전부(init/part-url/complete/abort) 같은 방식으로 422가
        # 나와야 한다 - 예전엔 각자 try/except를 반복했지만 지금은
        # register_upload_error_handlers() 하나가 전부 담당한다.
        cases = [
            ("initiate", "/api/admin/ocr/uploads/init", {
                "fileName": "data.exe", "fileSize": 10, "contentType": "text/plain",
            }),
            ("create_part_url", "/api/admin/ocr/uploads/part-url", {
                "uploadId": "u", "objectKey": "admin-rag-uploads/x", "partNumber": 1,
            }),
            ("complete", "/api/admin/ocr/uploads/complete", {
                "uploadId": "u", "objectKey": "admin-rag-uploads/x", "fileSize": 10,
                "parts": [{"partNumber": 1, "etag": "etag-1"}],
            }),
            ("abort", "/api/admin/ocr/uploads/abort", {
                "uploadId": "u", "objectKey": "admin-rag-uploads/x",
            }),
        ]
        for method_name, path, body in cases:
            with self.subTest(endpoint=path):
                with patch(
                    f"app.api.admin.upload_router.large_upload_service.{method_name}",
                    side_effect=LargeUploadValidationError("잘못된 요청입니다."),
                ):
                    response = self.client.post(path, json=body)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json(), {"detail": "잘못된 요청입니다."})

    def test_r2_storage_error_is_translated_to_503(self) -> None:
        with patch(
            "app.api.admin.upload_router.large_upload_service.initiate",
            side_effect=R2StorageError("R2에 연결할 수 없습니다."),
        ):
            response = self.client.post(
                "/api/admin/ocr/uploads/init",
                json={"fileName": "data.txt", "fileSize": 10, "contentType": "text/plain"},
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "R2에 연결할 수 없습니다."})


if __name__ == "__main__":
    unittest.main()
