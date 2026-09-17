import unittest
from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient
from starlette.datastructures import Headers

from app.api.auth.dependencies import get_current_user
from app.core.database import get_db
from app.main import app
from app.schemas.message import MessageResponse
from app.services.message_upload import validate_message_uploads


class MessageUploadValidationTest(unittest.IsolatedAsyncioTestCase):
    async def test_multiple_files_return_metadata_in_input_order(self) -> None:
        files = [
            _upload("first.png", b"image", "image/png"),
            _upload("report.pdf", b"%PDF-test", "application/pdf"),
        ]

        attachments = await validate_message_uploads(files)

        self.assertEqual([item.name for item in attachments], ["first.png", "report.pdf"])
        self.assertEqual([item.size for item in attachments], [5, 9])

    async def test_rejects_more_than_configured_file_count(self) -> None:
        files = [_upload(f"{index}.txt", b"text", "text/plain") for index in range(3)]

        with patch("app.services.message_upload.settings.message_max_files_per_request", 2):
            with self.assertRaises(HTTPException) as raised:
                await validate_message_uploads(files)

        self.assertEqual(raised.exception.status_code, 422)

    async def test_rejects_unsupported_extension(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            await validate_message_uploads([_upload("scan.dcm", b"dicom", "application/dicom")])

        self.assertEqual(raised.exception.status_code, 422)

    async def test_rejects_file_larger_than_configured_limit(self) -> None:
        with patch("app.services.message_upload.settings.message_max_file_size_mb", 0):
            with self.assertRaises(HTTPException) as raised:
                await validate_message_uploads([_upload("large.txt", b"x", "text/plain")])

        self.assertEqual(raised.exception.status_code, 413)


class MessageUploadApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id="test-user",
            auth_provider="local",
        )
        app.dependency_overrides[get_db] = lambda: object()
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)

    def test_multipart_endpoint_passes_all_files_to_service(self) -> None:
        result = MessageResponse(
            id="assistant-message",
            role="assistant",
            content="확인했습니다.",
            created_at=datetime.now(UTC),
        )
        with patch(
            "app.api.conversations.router.MessageService.send_message_with_uploads",
            new=AsyncMock(return_value=result),
        ) as sender:
            response = self.client.post(
                "/api/conversations/conversation-id/messages/upload",
                data={"content": "두 파일을 확인해 주세요."},
                files=[
                    ("files", ("first.png", b"image", "image/png")),
                    ("files", ("second.pdf", b"%PDF", "application/pdf")),
                ],
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["content"], "확인했습니다.")
        uploaded_files = sender.await_args.args[-1]
        self.assertEqual([file.filename for file in uploaded_files], ["first.png", "second.pdf"])


def _upload(name: str, content: bytes, content_type: str) -> UploadFile:
    return UploadFile(
        file=BytesIO(content),
        filename=name,
        headers=Headers({"content-type": content_type}),
    )


if __name__ == "__main__":
    unittest.main()
