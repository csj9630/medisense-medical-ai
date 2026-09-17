import asyncio
import unittest

import httpx
from PIL import Image
from io import BytesIO

from ai.ocr.contracts import OcrEngineResult, OcrLine, OcrProcessingConfig
from ai.ocr.errors import WebContentTooLargeError, WebUrlValidationError
from ai.ocr.extractors.web import (
    FetchedWebImage,
    WebImageCandidate,
    build_web_ocr_result,
    parse_web_document,
)
from app.services.web_document_fetcher import (
    FetchedWebPage,
    WebDocumentFetcher,
    WebFetchConfig,
    normalize_web_url,
)
from app.services.web_ocr_workflow import WebOcrWorkflowService


async def _public_resolver(_hostname: str, _port: int) -> list[str]:
    return ["93.184.216.34"]


class WebHtmlExtractorTest(unittest.TestCase):
    def test_extracts_main_content_and_resolves_images(self) -> None:
        parsed = parse_web_document(
            """
            <html><head><title>테스트 문서</title><style>hidden</style></head>
            <body><nav>메뉴</nav><main><h1>제목</h1><p>본문입니다.</p>
            <img src="/asset/chart.png" alt="검사 결과표"></main><footer>하단</footer></body></html>
            """,
            "https://example.com/article/1",
        )
        self.assertEqual(parsed.title, "테스트 문서")
        self.assertIn("# 제목", parsed.text)
        self.assertIn("본문입니다.", parsed.text)
        self.assertNotIn("메뉴", parsed.text)
        self.assertEqual(parsed.images[0].url, "https://example.com/asset/chart.png")
        self.assertEqual(parsed.images[0].label, "검사 결과표")

    def test_excludes_decorative_badge_image(self) -> None:
        parsed = parse_web_document(
            """
            <html><body><main>
              <h1>본문</h1><p>건강정보 본문입니다.</p>
              <img src="/chart.jpg" alt="진단 도표">
              <div class="copyright-license-badge">
                <img src="/open.png" alt="공공 라이선스 배지">
              </div>
            </main></body></html>
            """,
            "https://example.com/health/3",
        )
        self.assertEqual(len(parsed.images), 1)
        self.assertEqual(parsed.images[0].label, "진단 도표")

    def test_prefers_dense_content_container_over_filter_article(self) -> None:
        parsed = parse_web_document(
            """
            <html><head><title>건강정보</title></head><body>
              <article class="src-subject-wrap">
                <h6>주제별</h6><p>전체 건강문제 치료방법 검사방법 생활습관 관리</p>
              </article>
              <div class="data-content">
                <h1>고혈압</h1>
                <h2>개요</h2>
                <p>고혈압의 정의와 원인, 진단 및 치료에 관한 실제 건강정보 본문입니다.</p>
                <p>정기적인 혈압 측정과 생활습관 관리가 중요합니다.</p>
              </div>
            </body></html>
            """,
            "https://example.com/health/1",
        )
        self.assertIn("# 고혈압", parsed.text)
        self.assertIn("실제 건강정보 본문", parsed.text)
        self.assertNotIn("전체 건강문제 치료방법", parsed.text)

    def test_preserves_content_wrapped_by_form(self) -> None:
        parsed = parse_web_document(
            """
            <html><head><title>공공기관 건강정보</title></head><body>
              <article class="src-subject-wrap"><p>주제별 분류 메뉴</p></article>
              <form id="detailForm">
                <div class="data-content">
                  <h1>고혈압</h1>
                  <p>폼 내부에 있지만 삭제하면 안 되는 상세 건강정보입니다.</p>
                  <input type="hidden" name="contentId" value="1">
                </div>
              </form>
            </body></html>
            """,
            "https://example.com/health/2",
        )
        self.assertIn("고혈압", parsed.text)
        self.assertIn("삭제하면 안 되는 상세 건강정보", parsed.text)
        self.assertNotIn("주제별 분류 메뉴", parsed.text)

    def test_internal_image_ocr_is_appended_after_html_text(self) -> None:
        image_buffer = BytesIO()
        Image.new("RGB", (100, 100), "white").save(image_buffer, format="PNG")
        parsed = parse_web_document(
            "<html><head><title>문서</title></head><body><main><p>HTML 본문</p></main></body></html>",
            "https://example.com/",
        )
        result = build_web_ocr_result(
            parsed,
            [FetchedWebImage("https://example.com/chart.png", "차트", image_buffer.getvalue())],
            _ocr_config(),
            _FakeEngine(),
        )
        self.assertTrue(result.cleaned_text.startswith("HTML 본문"))
        self.assertIn("웹페이지 이미지 OCR: 차트", result.cleaned_text)
        self.assertIn("이미지 안의 글자", result.cleaned_text)
        self.assertEqual(result.ocr_image_count, 1)


class WebDocumentFetcherTest(unittest.TestCase):
    def test_normalize_rejects_credentials_non_web_scheme_and_custom_port(self) -> None:
        for url in (
            "file:///etc/passwd",
            "https://user:password@example.com/",
            "https://example.com:8443/",
        ):
            with self.subTest(url=url), self.assertRaises(WebUrlValidationError):
                normalize_web_url(url)

    def test_private_dns_result_is_rejected_before_http(self) -> None:
        async def private_resolver(_hostname: str, _port: int) -> list[str]:
            return ["127.0.0.1"]

        async def scenario() -> None:
            fetcher = WebDocumentFetcher(
                WebFetchConfig(),
                resolver=private_resolver,
                transport=httpx.MockTransport(
                    lambda _request: httpx.Response(200, text="should not run")
                ),
            )
            with self.assertRaises(WebUrlValidationError):
                await fetcher.fetch_page("https://example.com/")

        asyncio.run(scenario())

    def test_fetches_html_through_validated_ip_and_keeps_final_redirect_url(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.host, "93.184.216.34")
            self.assertEqual(request.headers["host"], "example.com")
            if request.url.path == "/start":
                return httpx.Response(302, headers={"location": "/final"})
            return httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                content="<html><body><p>완료</p></body></html>".encode(),
            )

        async def scenario() -> None:
            fetcher = WebDocumentFetcher(
                WebFetchConfig(),
                resolver=_public_resolver,
                transport=httpx.MockTransport(handler),
            )
            page = await fetcher.fetch_page("https://example.com/start")
            self.assertEqual(page.final_url, "https://example.com/final")
            self.assertIn("완료", page.html_text)

        asyncio.run(scenario())

    def test_stream_limit_rejects_oversized_html(self) -> None:
        async def scenario() -> None:
            fetcher = WebDocumentFetcher(
                WebFetchConfig(max_html_bytes=10),
                resolver=_public_resolver,
                transport=httpx.MockTransport(
                    lambda _request: httpx.Response(
                        200,
                        headers={"content-type": "text/html"},
                        content=b"x" * 11,
                    )
                ),
            )
            with self.assertRaises(WebContentTooLargeError):
                await fetcher.fetch_page("https://example.com/")

        asyncio.run(scenario())

    def test_total_image_budget_stops_additional_downloads(self) -> None:
        buffer = BytesIO()
        Image.new("RGB", (100, 100), "white").save(buffer, format="PNG")
        image_bytes = buffer.getvalue()

        async def scenario() -> None:
            fetcher = WebDocumentFetcher(
                WebFetchConfig(
                    max_image_bytes=len(image_bytes),
                    max_total_image_bytes=len(image_bytes),
                    image_concurrency=1,
                ),
                resolver=_public_resolver,
                transport=httpx.MockTransport(
                    lambda _request: httpx.Response(
                        200,
                        headers={"content-type": "image/png"},
                        content=image_bytes,
                    )
                ),
            )
            images, warnings = await fetcher.fetch_images(
                [
                    WebImageCandidate("https://example.com/one.png", "첫 이미지"),
                    WebImageCandidate("https://example.com/two.png", "둘째 이미지"),
                ]
            )
            self.assertEqual(len(images), 1)
            self.assertTrue(any("전체 수집 용량" in warning for warning in warnings))

        asyncio.run(scenario())

    def test_valid_jpeg_is_accepted_when_server_sends_invalid_content_type(self) -> None:
        buffer = BytesIO()
        Image.new("RGB", (120, 120), "white").save(buffer, format="JPEG")
        image_bytes = buffer.getvalue()

        async def scenario() -> None:
            fetcher = WebDocumentFetcher(
                WebFetchConfig(),
                resolver=_public_resolver,
                transport=httpx.MockTransport(
                    lambda _request: httpx.Response(
                        200,
                        headers={"content-type": "doesn/matter"},
                        content=image_bytes,
                    )
                ),
            )
            images, warnings = await fetcher.fetch_images(
                [WebImageCandidate("https://example.com/download?id=1", "진단 이미지")]
            )
            self.assertEqual(len(images), 1)
            self.assertEqual(warnings, [])

        asyncio.run(scenario())


class WebOcrWorkflowTest(unittest.TestCase):
    def test_web_result_uses_existing_admin_response_and_chunk_contract(self) -> None:
        class FakeFetcher:
            config = WebFetchConfig()

            async def fetch_page(self, url: str) -> FetchedWebPage:
                return FetchedWebPage(
                    requested_url=url,
                    final_url="https://example.com/final",
                    html_text="<html><head><title>의학 / 안내</title></head><body><main><p>충분한 웹페이지 본문입니다.</p></main></body></html>",
                )

            async def fetch_images(self, _candidates):
                return [], []

        async def scenario() -> None:
            service = WebOcrWorkflowService(
                FakeFetcher(),  # type: ignore[arg-type]
                _ocr_config(),
                max_text_chars=1_000,
                max_chunks=10,
            )
            result = await service.process_url(
                "https://example.com/start", 100, 10
            )
            self.assertEqual(result.source_type, "url")
            self.assertEqual(result.source_url, "https://example.com/final")
            self.assertEqual(result.document_name, "의학 / 안내")
            self.assertEqual(result.chunks, ["충분한 웹페이지 본문입니다."])

        asyncio.run(scenario())

class _FakeEngine:
    def extract_text(self, _image) -> OcrEngineResult:
        return OcrEngineResult(
            text="이미지 안의 글자",
            confidence=0.91,
            line_count=1,
            processing_time_seconds=0.01,
            lines=[OcrLine(text="이미지 안의 글자", confidence=0.91)],
        )


def _ocr_config() -> OcrProcessingConfig:
    return OcrProcessingConfig(
        max_file_bytes=1024,
        max_pdf_pages=1,
        native_text_min_chars=1,
        significant_image_area_ratio=0.1,
        pdf_render_dpi=100,
        max_image_side=500,
        max_image_pixels=1_000_000,
        paddle_device="cpu",
        paddle_language="korean",
        enable_denoise=False,
        enable_deskew=False,
    )


if __name__ == "__main__":
    unittest.main()
