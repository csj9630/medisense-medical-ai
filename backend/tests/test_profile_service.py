import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.services.profile import MAX_PROFILE_IMAGE_BYTES, ProfileService


class FakeUploadFile:
    def __init__(self, content: bytes, content_type: str) -> None:
        self._content = content
        self.content_type = content_type

    async def read(self, _size: int) -> bytes:
        return self._content


class UploadImageTest(unittest.IsolatedAsyncioTestCase):
    async def test_object_key_uses_forward_slashes_not_windows_backslashes(self) -> None:
        # 실제로 있었던 버그: pathlib.Path로 key를 만들면 Windows에서 "\"가 섞여
        # 들어가서 R2에 올라간 뒤 공개 URL이 깨졌다(프로필 이미지가 항상 엑박으로
        # 나왔음). S3/R2 오브젝트 키는 OS와 무관하게 항상 "/"여야 한다.
        db = MagicMock()
        service = ProfileService(db)
        user = MagicMock(id=uuid4(), profile_image_url=None)
        file = FakeUploadFile(b"fake-image-bytes", "image/png")

        with patch("app.services.profile.r2_storage") as mock_r2:
            mock_r2.upload.return_value = "https://pub.example.com/profiles/some/key.png"
            await service.upload_image(user, file)

        called_key = mock_r2.upload.call_args.args[1]
        self.assertNotIn("\\", called_key)
        self.assertTrue(called_key.startswith(f"profiles/{user.id}/"))
        self.assertTrue(called_key.endswith(".png"))

    async def test_saves_returned_image_url_on_user(self) -> None:
        db = MagicMock()
        service = ProfileService(db)
        user = MagicMock(id=uuid4(), profile_image_url=None)
        file = FakeUploadFile(b"fake-image-bytes", "image/jpeg")

        with patch("app.services.profile.r2_storage") as mock_r2:
            mock_r2.upload.return_value = "https://pub.example.com/profiles/x/y.jpg"
            result = await service.upload_image(user, file)

        self.assertEqual(result.profile_image_url, "https://pub.example.com/profiles/x/y.jpg")

    async def test_rejects_unsupported_content_type(self) -> None:
        from fastapi import HTTPException

        db = MagicMock()
        service = ProfileService(db)
        user = MagicMock(id=uuid4())
        file = FakeUploadFile(b"not-an-image", "application/pdf")

        with self.assertRaises(HTTPException) as ctx:
            await service.upload_image(user, file)
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_rejects_oversized_file(self) -> None:
        from fastapi import HTTPException

        db = MagicMock()
        service = ProfileService(db)
        user = MagicMock(id=uuid4())
        file = FakeUploadFile(b"x" * (MAX_PROFILE_IMAGE_BYTES + 1), "image/png")

        with self.assertRaises(HTTPException) as ctx:
            await service.upload_image(user, file)
        self.assertEqual(ctx.exception.status_code, 413)


if __name__ == "__main__":
    unittest.main()
