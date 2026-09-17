"""SSRF 방어와 크기 제한을 적용해 공개 웹 문서와 이미지를 수집합니다."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from io import BytesIO
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from PIL import Image, UnidentifiedImageError

from ai.ocr.errors import (
    WebContentTooLargeError,
    WebFetchError,
    WebUnsupportedContentError,
    WebUrlValidationError,
)
from ai.ocr.extractors.web import FetchedWebImage, WebImageCandidate

DnsResolver = Callable[[str, int], Awaitable[list[str]]]
HTML_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}


@dataclass(frozen=True)
class WebFetchConfig:
    max_url_length: int = 500
    max_html_bytes: int = 5 * 1024 * 1024
    max_redirects: int = 3
    connect_timeout_seconds: float = 5
    read_timeout_seconds: float = 15
    max_images: int = 20
    max_image_bytes: int = 5 * 1024 * 1024
    max_total_image_bytes: int = 30 * 1024 * 1024
    image_concurrency: int = 4
    max_image_pixels: int = 40_000_000


@dataclass(frozen=True)
class FetchedWebPage:
    requested_url: str
    final_url: str
    html_text: str


class WebDocumentFetcher:
    def __init__(
        self,
        config: WebFetchConfig,
        *,
        resolver: DnsResolver | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self.resolver = resolver or _resolve_public_addresses
        self.transport = transport

    async def fetch_page(self, url: str) -> FetchedWebPage:
        requested_url = normalize_web_url(url, self.config.max_url_length)
        timeout = httpx.Timeout(
            connect=self.config.connect_timeout_seconds,
            read=self.config.read_timeout_seconds,
            write=self.config.read_timeout_seconds,
            pool=self.config.connect_timeout_seconds,
        )
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=timeout,
            trust_env=False,
            transport=self.transport,
            headers={"User-Agent": "TheGPT-AdminOCR/1.0", "Accept": "text/html,application/xhtml+xml"},
        ) as client:
            current_url = requested_url
            for redirect_count in range(self.config.max_redirects + 1):
                addresses = await self._validate_destination(current_url)
                response, content = await _send_limited(
                    client,
                    current_url,
                    self.config.max_html_bytes,
                    connect_ip=addresses[0],
                )
                if response.status_code in {301, 302, 303, 307, 308}:
                    if redirect_count >= self.config.max_redirects:
                        raise WebFetchError("웹페이지 리디렉션 횟수가 허용 한도를 초과했습니다.")
                    location = response.headers.get("location", "").strip()
                    if not location:
                        raise WebFetchError("웹페이지 리디렉션 주소가 비어 있습니다.")
                    next_url = normalize_web_url(
                        urljoin(current_url, location), self.config.max_url_length
                    )
                    if urlsplit(current_url).scheme == "https" and urlsplit(next_url).scheme == "http":
                        raise WebUrlValidationError("HTTPS에서 HTTP로 낮아지는 리디렉션은 허용하지 않습니다.")
                    current_url = next_url
                    continue

                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    raise WebFetchError(
                        f"웹페이지 요청이 HTTP {response.status_code}로 실패했습니다."
                    ) from exc
                content_type = _content_type(response)
                if content_type not in HTML_CONTENT_TYPES:
                    raise WebUnsupportedContentError(
                        f"HTML 웹페이지만 수집할 수 있습니다. 응답 형식: {content_type or '알 수 없음'}"
                    )
                encoding = response.encoding or "utf-8"
                return FetchedWebPage(
                    requested_url=requested_url,
                    final_url=current_url,
                    html_text=content.decode(encoding, errors="replace"),
                )

        raise WebFetchError("웹페이지를 가져오지 못했습니다.")

    async def fetch_images(
        self,
        candidates: list[WebImageCandidate],
    ) -> tuple[list[FetchedWebImage], list[str]]:
        selected = candidates[: self.config.max_images]
        warnings: list[str] = []
        if len(candidates) > len(selected):
            warnings.append(
                f"내부 이미지는 최대 {self.config.max_images}개까지만 OCR합니다."
            )
        if not selected:
            return [], warnings

        timeout = httpx.Timeout(
            connect=self.config.connect_timeout_seconds,
            read=self.config.read_timeout_seconds,
            write=self.config.read_timeout_seconds,
            pool=self.config.connect_timeout_seconds,
        )
        semaphore = asyncio.Semaphore(max(1, self.config.image_concurrency))
        budget_lock = asyncio.Lock()
        remaining_budget = self.config.max_total_image_bytes
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=timeout,
            trust_env=False,
            transport=self.transport,
            headers={"User-Agent": "TheGPT-AdminOCR/1.0", "Accept": "image/jpeg,image/png,image/webp"},
        ) as client:
            async def fetch_one(index: int, candidate: WebImageCandidate):
                nonlocal remaining_budget
                async with semaphore:
                    async with budget_lock:
                        reservation = min(
                            self.config.max_image_bytes, remaining_budget
                        )
                        remaining_budget -= reservation
                    if reservation <= 0:
                        return None, f"내부 이미지 #{index}: 전체 수집 용량 한도에 도달했습니다."
                    try:
                        image = await self._fetch_image(
                            client, candidate, max_bytes=reservation
                        )
                    except Exception as exc:
                        async with budget_lock:
                            remaining_budget += reservation
                        return None, (
                            f"내부 이미지 #{index} 수집을 건너뛰었습니다 "
                            f"({candidate.label}): {exc}"
                        )
                    async with budget_lock:
                        remaining_budget += reservation - len(image.content)
                    return image, None

            results = await asyncio.gather(
                *(fetch_one(index, item) for index, item in enumerate(selected, start=1))
            )

        images: list[FetchedWebImage] = []
        total_bytes = 0
        for image, warning in results:
            if warning:
                warnings.append(warning)
            if image is None:
                continue
            if total_bytes + len(image.content) > self.config.max_total_image_bytes:
                warnings.append("내부 이미지 전체 수집 용량 한도에 도달해 나머지를 건너뛰었습니다.")
                break
            total_bytes += len(image.content)
            images.append(image)
        return images, list(dict.fromkeys(warnings))

    async def _fetch_image(
        self,
        client: httpx.AsyncClient,
        candidate: WebImageCandidate,
        *,
        max_bytes: int,
    ) -> FetchedWebImage:
        current_url = normalize_web_url(candidate.url, self.config.max_url_length)
        for redirect_count in range(self.config.max_redirects + 1):
            addresses = await self._validate_destination(current_url)
            response, content = await _send_limited(
                client,
                current_url,
                max_bytes,
                connect_ip=addresses[0],
            )
            if response.status_code in {301, 302, 303, 307, 308}:
                if redirect_count >= self.config.max_redirects:
                    raise WebFetchError("이미지 리디렉션 한도를 초과했습니다.")
                location = response.headers.get("location", "").strip()
                current_url = normalize_web_url(
                    urljoin(current_url, location), self.config.max_url_length
                )
                continue
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise WebFetchError(f"HTTP {response.status_code}") from exc
            # 일부 공공기관 다운로드 Endpoint는 JPEG에도 `doesn/matter`처럼 잘못된
            # Content-Type을 반환합니다. HTTP Header가 아니라 아래 실제 File Signature와
            # Pillow Decode 결과를 최종 신뢰 경계로 사용합니다.
            _verify_image(content, self.config.max_image_pixels)
            return FetchedWebImage(
                url=current_url,
                label=candidate.label,
                content=content,
            )
        raise WebFetchError("이미지를 가져오지 못했습니다.")

    async def _validate_destination(self, url: str) -> list[str]:
        parsed = urlsplit(url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        addresses = await self.resolver(parsed.hostname or "", port)
        if not addresses:
            raise WebUrlValidationError("웹 주소의 DNS 결과를 찾지 못했습니다.")
        validated: list[str] = []
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
                ip = ip.ipv4_mapped
            if not ip.is_global:
                raise WebUrlValidationError("공개 인터넷 주소만 수집할 수 있습니다.")
            validated.append(str(ip))
        return sorted(set(validated), key=lambda value: ipaddress.ip_address(value).version)


def normalize_web_url(url: str, max_length: int = 500) -> str:
    value = url.strip()
    if not value or len(value) > max_length:
        raise WebUrlValidationError(f"URL은 1자 이상 {max_length}자 이하여야 합니다.")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise WebUrlValidationError("올바른 웹 URL을 입력해 주세요.") from exc
    if parsed.scheme not in {"http", "https"}:
        raise WebUrlValidationError("http 또는 https URL만 입력할 수 있습니다.")
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise WebUrlValidationError("호스트가 있으며 인증 정보가 없는 URL만 허용합니다.")
    default_port = 443 if parsed.scheme == "https" else 80
    if port is not None and port != default_port:
        raise WebUrlValidationError("기본 웹 포트(80/443)만 허용합니다.")
    try:
        hostname = parsed.hostname.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise WebUrlValidationError("URL 호스트 이름을 해석하지 못했습니다.") from exc
    netloc = hostname if port is None else f"{hostname}:{port}"
    if ":" in hostname and not hostname.startswith("["):
        netloc = f"[{hostname}]" if port is None else f"[{hostname}]:{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path or "/", parsed.query, ""))


async def _resolve_public_addresses(hostname: str, port: int) -> list[str]:
    try:
        records = await asyncio.to_thread(
            socket.getaddrinfo,
            hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise WebUrlValidationError("웹 주소의 DNS 조회에 실패했습니다.") from exc
    return sorted({record[4][0] for record in records})


async def _send_limited(
    client: httpx.AsyncClient,
    url: str,
    max_bytes: int,
    *,
    connect_ip: str,
) -> tuple[httpx.Response, bytes]:
    parsed = urlsplit(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    ip_host = f"[{connect_ip}]" if ":" in connect_ip else connect_ip
    network_url = urlunsplit(
        (parsed.scheme, f"{ip_host}:{port}", parsed.path, parsed.query, "")
    )
    try:
        async with client.stream(
            "GET",
            network_url,
            headers={"Host": parsed.netloc},
            extensions={"sni_hostname": parsed.hostname},
        ) as response:
            declared_length = response.headers.get("content-length")
            if declared_length and declared_length.isdigit() and int(declared_length) > max_bytes:
                raise WebContentTooLargeError("웹 리소스가 허용 용량을 초과했습니다.")
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    raise WebContentTooLargeError("웹 리소스가 허용 용량을 초과했습니다.")
                chunks.append(chunk)
            return response, b"".join(chunks)
    except (WebContentTooLargeError, WebUrlValidationError):
        raise
    except httpx.TimeoutException as exc:
        raise WebFetchError("웹 리소스 요청 시간이 초과되었습니다.") from exc
    except httpx.RequestError as exc:
        raise WebFetchError("웹 리소스에 연결하지 못했습니다.") from exc


def _content_type(response: httpx.Response) -> str:
    return response.headers.get("content-type", "").split(";", 1)[0].strip().lower()


def _verify_image(content: bytes, max_pixels: int) -> None:
    try:
        with Image.open(BytesIO(content)) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                raise WebUnsupportedContentError("지원하지 않는 실제 이미지 형식입니다.")
            if image.width < 64 or image.height < 64:
                raise WebUnsupportedContentError("OCR하기에는 이미지가 너무 작습니다.")
            if image.width * image.height > max_pixels:
                raise WebContentTooLargeError("이미지 해상도가 허용 범위를 초과했습니다.")
            image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise WebUnsupportedContentError("이미지 데이터를 확인하지 못했습니다.") from exc
