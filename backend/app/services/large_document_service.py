"""R2의 대용량 RAG 원본을 일정한 메모리 사용량으로 분석합니다."""

import asyncio
import codecs
import io
import json
import logging
from collections.abc import Iterable, Iterator
from pathlib import Path
from uuid import uuid4
from zipfile import BadZipFile, ZipFile, ZipInfo

from ai.ocr import OcrDocumentInput, analyze_document
from ai.ocr.errors import DocumentValidationError, OcrError
from app.core.config import Settings, settings
from app.schemas.admin import OcrDocumentResponse
from app.services.large_upload_service import UPLOAD_PREFIX
from app.services.ocr_chunk_service import find_natural_boundary
from app.services.ocr_workflow import ocr_workflow_service
from app.services.r2_storage import R2StorageError, R2StorageService, rag_r2_storage

logger = logging.getLogger(__name__)

MIB = 1024**2
ARTIFACT_PREFIX = "admin-rag-artifacts/"
ARTIFACT_PART_SIZE = 8 * MIB
TEXT_EXTENSIONS = {".json", ".jsonl", ".csv", ".txt"}
BINARY_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".docx", ".pptx"}
PREVIEW_CHARACTER_LIMIT = 100_000
PREVIEW_CHUNK_LIMIT = 20


class _StreamingChunker:
    """R2에서 조금씩 받은 텍스트를 그때그때 청크로 잘라낸다 - 문서 전체를
    메모리에 모으지 않으므로(8GB까지 처리해야 함) `ai/rag/chunking.py`의
    토큰 기반 청커는 못 쓰지만(전체 텍스트가 str로 다 있어야 함), 지금 갖고
    있는 버퍼 안에서는 자연 경계(문단/문장/공백)를 찾는 게 가능하다.

    2026-09-07: 원래는 그냥 `chunk_size` 글자 수로 뚝 잘랐다(문장 중간이든
    단어 중간이든 상관없이) - 관리자 업로드 소용량 경로(ocr_chunk_service.
    create_chunks)는 이미 자연 경계를 찾고 있었는데 여기만 빠져 있었다.
    같은 `_find_natural_boundary()`를 재사용한다 - 그 함수는 절대 위치를
    받으므로, "지금 버퍼"를 하나의 완결된 text처럼(start=0) 넘기면 그대로
    동작한다."""

    def __init__(self, chunk_size: int, overlap: int) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.buffer = ""

    def feed(self, text: str) -> Iterator[str]:
        self.buffer += text
        while len(self.buffer) >= self.chunk_size:
            maximum_end = min(self.chunk_size, len(self.buffer))
            end = find_natural_boundary(self.buffer, 0, maximum_end, self.chunk_size)
            chunk = self.buffer[:end].strip()
            if chunk:
                yield chunk
            # Overlap 뒤에도 버퍼가 반드시 줄어들도록 보장한다(무한루프 방지).
            self.buffer = self.buffer[max(end - self.overlap, 1) :]

    def finish(self) -> Iterator[str]:
        chunk = self.buffer.strip()
        self.buffer = ""
        if chunk:
            yield chunk


class _ChunkArtifactWriter:
    """Chunk JSONL을 R2 multipart로 올려 전체 결과를 메모리에 보관하지 않습니다."""

    def __init__(self, storage: R2StorageService) -> None:
        self.storage = storage
        self.key = f"{ARTIFACT_PREFIX}{uuid4().hex}.jsonl"
        self.upload_id = storage.create_multipart_upload(
            key=self.key,
            content_type="application/x-ndjson",
            file_name="chunks.jsonl",
            file_size=0,
        )
        self.buffer = bytearray()
        self.parts: list[dict[str, int | str]] = []
        self.closed = False

    def write(self, chunk: str) -> None:
        self.buffer.extend(
            json.dumps({"text": chunk}, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        )
        self.buffer.extend(b"\n")
        if len(self.buffer) >= ARTIFACT_PART_SIZE:
            self._flush()

    def complete(self) -> str:
        if self.closed:
            return self.key
        self._flush()
        if not self.parts:
            raise DocumentValidationError("분석할 텍스트가 없습니다.")
        self.storage.complete_multipart_upload(
            key=self.key,
            upload_id=self.upload_id,
            parts=self.parts,
        )
        self.closed = True
        return self.key

    def abort(self) -> None:
        if self.closed:
            return
        try:
            self.storage.abort_multipart_upload(key=self.key, upload_id=self.upload_id)
        except R2StorageError:
            logger.exception("Chunk artifact multipart 정리 실패: key=%s", self.key)
        self.closed = True

    def _flush(self) -> None:
        if not self.buffer:
            return
        part_number = len(self.parts) + 1
        etag = self.storage.upload_part(
            key=self.key,
            upload_id=self.upload_id,
            part_number=part_number,
            content=bytes(self.buffer),
        )
        self.parts.append({"PartNumber": part_number, "ETag": etag})
        self.buffer.clear()


class _R2RangeReader(io.RawIOBase):
    """zipfile이 필요한 구간만 R2 Range GET으로 읽는 seek 가능한 Reader입니다."""

    def __init__(self, storage: R2StorageService, key: str, size: int) -> None:
        self.storage = storage
        self.key = key
        self.size = size
        self.position = 0
        self.cache_start = 0
        self.cache = b""

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.position

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            target = offset
        elif whence == io.SEEK_CUR:
            target = self.position + offset
        elif whence == io.SEEK_END:
            target = self.size + offset
        else:
            raise ValueError("올바르지 않은 seek 기준입니다.")
        if target < 0:
            raise ValueError("파일 시작 전으로 이동할 수 없습니다.")
        self.position = min(target, self.size)
        return self.position

    def read(self, size: int = -1) -> bytes:
        if self.position >= self.size:
            return b""
        requested = self.size - self.position if size is None or size < 0 else size
        requested = min(requested, self.size - self.position)
        output = bytearray()
        while requested > 0:
            if not self._cache_contains(self.position):
                end = min(self.position + 8 * MIB, self.size) - 1
                self.cache_start = self.position
                self.cache = self.storage.get_object_range(self.key, self.position, end)
                if not self.cache:
                    break
            offset = self.position - self.cache_start
            take = min(requested, len(self.cache) - offset)
            if take <= 0:
                self.cache = b""
                continue
            output.extend(self.cache[offset : offset + take])
            self.position += take
            requested -= take
        return bytes(output)

    def _cache_contains(self, position: int) -> bool:
        return self.cache_start <= position < self.cache_start + len(self.cache)


class LargeDocumentService:
    def __init__(
        self,
        storage: R2StorageService = rag_r2_storage,
        app_settings: Settings = settings,
    ) -> None:
        self.storage = storage
        self.max_file_bytes = app_settings.ocr_max_file_size_mb * MIB
        self.inline_file_bytes = app_settings.ocr_inline_file_size_mb * MIB
        self.max_archive_uncompressed_bytes = (
            app_settings.ocr_large_archive_uncompressed_size_mb * MIB
        )
        self.max_archive_entries = app_settings.ocr_max_office_archive_entries

    async def process(
        self,
        *,
        object_key: str,
        file_name: str,
        file_size: int,
        content_type: str,
        chunk_size: int,
        overlap: int,
        progress_callback=None,
    ) -> OcrDocumentResponse:
        return await asyncio.to_thread(
            self._process_sync,
            object_key,
            file_name,
            file_size,
            content_type,
            chunk_size,
            overlap,
            progress_callback,
        )

    def _process_sync(
        self,
        object_key: str,
        file_name: str,
        file_size: int,
        content_type: str,
        chunk_size: int,
        overlap: int,
        progress_callback,
    ) -> OcrDocumentResponse:
        del content_type
        safe_name = Path(file_name.replace("\\", "/")).name
        extension = Path(safe_name).suffix.lower()
        self._validate_source(object_key, file_size, extension)
        metadata = self.storage.head_object(object_key)
        if int(metadata.get("ContentLength", -1)) != file_size:
            raise DocumentValidationError("업로드한 파일의 크기 정보를 확인할 수 없습니다.")

        writer = _ChunkArtifactWriter(self.storage)
        chunker = _StreamingChunker(chunk_size, overlap)
        preview_text = ""
        preview_chunks: list[str] = []
        character_count = 0
        chunk_count = 0
        notes = ["대용량 원본을 R2에서 스트리밍 방식으로 분석했습니다."]

        def consume(pieces: Iterable[str]) -> None:
            nonlocal preview_text, character_count, chunk_count
            for piece in pieces:
                character_count += len(piece)
                if len(preview_text) < PREVIEW_CHARACTER_LIMIT:
                    preview_text += piece[: PREVIEW_CHARACTER_LIMIT - len(preview_text)]
                for chunk in chunker.feed(piece):
                    writer.write(chunk)
                    chunk_count += 1
                    if len(preview_chunks) < PREVIEW_CHUNK_LIMIT:
                        preview_chunks.append(chunk)

        try:
            self._report(progress_callback, "extracting", 10, "R2 원본 분석을 시작했습니다.")
            if extension in TEXT_EXTENSIONS:
                consume(_decode_byte_chunks(self.storage.iter_object_chunks(object_key)))
            elif extension == ".zip":
                zip_notes, zip_pieces = self._iter_zip_text(object_key, file_size, progress_callback)
                consume(zip_pieces)
                notes.extend(zip_notes)
            else:
                raise DocumentValidationError(
                    "20MB를 초과하는 파일은 JSON, JSONL, CSV, TXT 또는 ZIP만 분석할 수 있습니다."
                )

            for chunk in chunker.finish():
                writer.write(chunk)
                chunk_count += 1
                if len(preview_chunks) < PREVIEW_CHUNK_LIMIT:
                    preview_chunks.append(chunk)
            artifact_key = writer.complete()
        except Exception:
            writer.abort()
            raise

        if not preview_chunks:
            raise DocumentValidationError("분석할 텍스트가 없습니다.")
        if character_count > len(preview_text):
            notes.append(f"추출 텍스트는 앞 {PREVIEW_CHARACTER_LIMIT:,}자만 미리 표시합니다.")
        if chunk_count > len(preview_chunks):
            notes.append(f"Chunk는 앞 {PREVIEW_CHUNK_LIMIT}개만 미리 표시합니다.")
        if extension in {".json", ".jsonl", ".csv"}:
            notes.append("대용량 구조화 파일은 원문을 보존해 스트리밍 청킹했습니다.")

        self._report(progress_callback, "finalizing", 99, "대용량 분석 결과를 구성했습니다.")
        return OcrDocumentResponse(
            documentName=safe_name,
            pageCount=None,
            characterCount=character_count,
            estimatedChunks=chunk_count,
            confidence=100.0,
            extractedText=preview_text,
            chunks=preview_chunks,
            readiness="review" if any("건너뛰" in note for note in notes) else "ready",
            notes=notes,
            chunk_artifact_key=artifact_key,
            original_object_key=object_key,
        )

    def _iter_zip_text(self, object_key: str, file_size: int, progress_callback):
        notes: list[str] = []

        def pieces() -> Iterator[str]:
            successful = 0
            skipped = 0
            reader = _R2RangeReader(self.storage, object_key, file_size)
            try:
                with ZipFile(reader) as archive:
                    members = [entry for entry in archive.infolist() if not entry.is_dir()]
                    if len(members) > self.max_archive_entries:
                        raise DocumentValidationError("ZIP 내부 파일 수가 허용 한도를 초과했습니다.")
                    total_size = sum(entry.file_size for entry in members)
                    if total_size > self.max_archive_uncompressed_bytes:
                        raise DocumentValidationError("ZIP 압축 해제 예상 크기가 허용 한도를 초과했습니다.")
                    for index, entry in enumerate(members):
                        extension = Path(entry.filename).suffix.lower()
                        display_name = _safe_member_name(entry)
                        if entry.flag_bits & 0x1:
                            raise DocumentValidationError("암호화된 ZIP 파일은 지원하지 않습니다.")
                        self._report(
                            progress_callback,
                            "extracting",
                            10 + int(((index + 1) / max(len(members), 1)) * 78),
                            f"ZIP 내부 {index + 1}/{len(members)} 파일을 분석하고 있습니다.",
                        )
                        if extension in TEXT_EXTENSIONS:
                            yield f"\n\n## ZIP 내부 파일: {display_name}\n\n"
                            with archive.open(entry) as member:
                                yield from _decode_stream(member)
                            successful += 1
                            continue
                        if extension in BINARY_EXTENSIONS and entry.file_size <= self.inline_file_bytes:
                            try:
                                result = analyze_document(
                                    OcrDocumentInput(
                                        file_name=display_name,
                                        content_type="application/octet-stream",
                                        content=archive.read(entry),
                                    ),
                                    ocr_workflow_service.config,
                                )
                            except OcrError as exc:
                                notes.append(f"ZIP 내부 {display_name} 건너뜀: {exc}")
                                skipped += 1
                                continue
                            yield f"\n\n## ZIP 내부 파일: {display_name}\n\n{result.cleaned_text}"
                            successful += 1
                            continue
                        skipped += 1
                    if successful == 0:
                        raise DocumentValidationError("ZIP 내부에서 분석할 수 있는 문서를 찾지 못했습니다.")
                    notes.insert(0, f"ZIP 내부 문서 {successful}개를 통합했습니다.")
                    if skipped:
                        notes.append(f"지원하지 않거나 20MB를 초과한 내부 파일 {skipped}개를 건너뛰었습니다.")
            except (BadZipFile, NotImplementedError, RuntimeError, OSError, ValueError) as exc:
                if isinstance(exc, DocumentValidationError):
                    raise
                raise DocumentValidationError("손상되었거나 읽을 수 없는 ZIP 파일입니다.") from exc

        return notes, pieces()

    def _validate_source(self, object_key: str, file_size: int, extension: str) -> None:
        if not object_key.startswith(UPLOAD_PREFIX) or ".." in object_key.split("/"):
            raise DocumentValidationError("올바르지 않은 R2 Object Key입니다.")
        if not 0 < file_size <= self.max_file_bytes:
            raise DocumentValidationError("파일은 8GB 이하만 업로드할 수 있습니다.")
        if extension not in TEXT_EXTENSIONS | BINARY_EXTENSIONS | {".zip"}:
            raise DocumentValidationError("지원하지 않는 파일 형식입니다.")

    @staticmethod
    def _report(callback, stage: str, progress: int, message: str) -> None:
        if callback is not None:
            callback(stage, max(0, min(progress, 99)), message)


def iter_chunk_artifact(
    key: str,
    storage: R2StorageService = rag_r2_storage,
) -> Iterator[str]:
    pending = b""
    for block in storage.iter_object_chunks(key):
        pending += block
        lines = pending.split(b"\n")
        pending = lines.pop()
        for line in lines:
            if line:
                yield _artifact_chunk(line)
    if pending:
        yield _artifact_chunk(pending)


def _artifact_chunk(line: bytes) -> str:
    try:
        value = json.loads(line)
        text = value["text"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise DocumentValidationError("저장된 Chunk 결과가 손상되었습니다.") from exc
    if not isinstance(text, str) or not text.strip():
        raise DocumentValidationError("저장된 Chunk 결과에 빈 Chunk가 있습니다.")
    return text


def _decode_byte_chunks(chunks: Iterable[bytes]) -> Iterator[str]:
    iterator = iter(chunks)
    first = next(iterator, b"")
    if not first:
        return
    encoding = _detect_encoding(first)
    decoder = codecs.getincrementaldecoder(encoding)(errors="strict")
    try:
        text = decoder.decode(first, final=False)
        if "\x00" in text:
            raise UnicodeDecodeError(encoding, first, 0, 1, "NUL 문자")
        if text:
            yield text
        for block in iterator:
            text = decoder.decode(block, final=False)
            if "\x00" in text:
                raise UnicodeDecodeError(encoding, block, 0, 1, "NUL 문자")
            if text:
                yield text
        tail = decoder.decode(b"", final=True)
        if tail:
            yield tail
    except UnicodeDecodeError as exc:
        raise DocumentValidationError(
            "텍스트 인코딩을 읽을 수 없습니다. UTF-8, UTF-16 또는 CP949로 저장해 주세요."
        ) from exc


def _decode_stream(stream) -> Iterator[str]:
    def chunks() -> Iterator[bytes]:
        while True:
            block = stream.read(MIB)
            if not block:
                break
            yield bytes(block)

    yield from _decode_byte_chunks(chunks())


def _detect_encoding(first: bytes) -> str:
    if first.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"
    try:
        codecs.getincrementaldecoder("utf-8-sig")(errors="strict").decode(
            first,
            final=False,
        )
    except UnicodeDecodeError:
        return "cp949"
    return "utf-8-sig"


def _safe_member_name(entry: ZipInfo) -> str:
    return entry.filename.replace("\\", "/").replace("\r", " ").replace("\n", " ")


large_document_service = LargeDocumentService()
