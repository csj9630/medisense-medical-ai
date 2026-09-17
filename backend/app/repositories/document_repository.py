"""OCR 문서와 Chunk를 같은 DB Transaction으로 저장합니다."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.generated import AdminDocuments, ChunkEmbeddings, DocumentChunks
from app.repositories.document_chunk import pad_embedding

logger = logging.getLogger(__name__)


class DocumentPersistenceError(Exception):
    """문서 또는 Chunk 저장 Transaction이 실패했을 때 발생합니다."""


@dataclass(frozen=True)
class SavedDocument:
    document_id: UUID
    chunk_count: int


class DocumentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    @contextmanager
    def _rollback_on_error(self, message: str) -> Iterator[None]:
        """저장 메서드 4개(save_with_chunks/begin_staged_save/append_staged_chunks/
        finish_staged_save/abort_staged_save)가 전부 반복하던 "실패하면 rollback
        하고 DocumentPersistenceError로 바꿔서 던진다" 패턴을 한 곳으로 모았다
        (2026-09-04). 이미 DocumentPersistenceError인 경우(메서드 자체가 명시적으로
        던진 것 - 예: "저장할 Provider가 없습니다")는 메시지를 덮어쓰지 않고 그대로
        전파한다."""
        try:
            yield
        except DocumentPersistenceError:
            self.db.rollback()
            raise
        except Exception as exc:
            self.db.rollback()
            logger.exception(message)
            raise DocumentPersistenceError(message) from exc

    def save_with_chunks(
        self,
        *,
        original_file_url: str,
        extracted_text: str,
        chunks: list[str],
        embeddings_by_provider: dict[str, list[list[float]]],
        chunk_metadata: dict | None = None,
    ) -> SavedDocument:
        """문서·Chunk·Provider별 Vector를 하나의 Transaction으로 저장합니다.

        `chunk_metadata`: RAG 검색 소프트 부스트(rag_search_service._boost_multiplier)와
        답변 출처 표시(ai/consultation/context.py)가 읽는 source/source_tier/department
        등 - 생략하면(기존 호출부 그대로) NULL이라 부스트도 출처 표시도 없이 중립으로
        검색만 된다(하위호환, 2026-09-03 admin_ocr.py에 자동 채움 추가하며 도입)."""

        if not embeddings_by_provider:
            raise DocumentPersistenceError("저장할 Embedding Provider가 없습니다.")
        if any(len(chunks) != len(vectors) for vectors in embeddings_by_provider.values()):
            raise DocumentPersistenceError("Chunk와 Provider별 Embedding 개수가 일치하지 않습니다.")

        with self._rollback_on_error("Neon DB에 OCR 문서를 저장하지 못했습니다."):
            document = AdminDocuments(
                original_file_url=original_file_url,
                ocr_extracted_text=extracted_text,
                ocr_status="completed",
            )
            self.db.add(document)
            # DB가 생성하는 UUID를 모든 Chunk의 FK에 사용하기 위해 먼저 flush합니다.
            self.db.flush()
            if document.id is None:
                raise DocumentPersistenceError("저장된 문서 ID를 확인할 수 없습니다.")

            rows = [
                DocumentChunks(
                    document_id=document.id,
                    chunk_index=index,
                    chunk_text=chunk,
                    chunk_metadata=chunk_metadata,
                )
                for index, chunk in enumerate(chunks)
            ]
            self.db.add_all(rows)
            # Chunk UUID를 chunk_embeddings FK로 사용하기 위해 같은 Transaction에서 flush합니다.
            self.db.flush()
            embedding_rows = [
                ChunkEmbeddings(
                    chunk_id=chunk.id,
                    provider_name=provider_name,
                    dimension=len(vector),
                    embedding=pad_embedding(vector),
                )
                for provider_name, vectors in embeddings_by_provider.items()
                for chunk, vector in zip(rows, vectors, strict=True)
            ]
            self.db.add_all(embedding_rows)
            self.db.commit()
            logger.info(
                "[OCR SAVE] neon insert complete: document_id=%s chunks=%d providers=%s",
                document.id,
                len(rows),
                list(embeddings_by_provider),
            )
            return SavedDocument(document_id=document.id, chunk_count=len(rows))

    def begin_staged_save(self, *, original_file_url: str, extracted_text: str) -> UUID:
        """대용량 Chunk 배치 저장을 시작하고 검색 비노출 상태로 문서를 생성합니다."""

        with self._rollback_on_error("Neon DB에 OCR 문서를 생성하지 못했습니다."):
            document = AdminDocuments(
                original_file_url=original_file_url,
                ocr_extracted_text=extracted_text,
                ocr_status="processing",
            )
            self.db.add(document)
            self.db.flush()
            if document.id is None:
                raise DocumentPersistenceError("저장된 문서 ID를 확인할 수 없습니다.")
            self.db.commit()
            return document.id

    def append_staged_chunks(
        self,
        *,
        document_id: UUID,
        start_index: int,
        chunks: list[str],
        embeddings_by_provider: dict[str, list[list[float]]],
        chunk_metadata: dict | None = None,
    ) -> None:
        """`chunk_metadata`: 문서 하나를 배치 여러 개로 나눠 저장하는 도중에도 값이
        흔들리면 안 되므로, 호출부(admin_ocr.py)가 스테이지드 저장을 시작할 때 한 번
        정한 같은 dict를 배치마다 그대로 넘긴다(save_with_chunks와 동일한 용도)."""
        if not embeddings_by_provider or any(
            len(chunks) != len(vectors) for vectors in embeddings_by_provider.values()
        ):
            raise DocumentPersistenceError("Chunk와 Provider별 Embedding 개수가 일치하지 않습니다.")
        with self._rollback_on_error("Neon DB에 OCR Chunk 배치를 저장하지 못했습니다."):
            rows = [
                DocumentChunks(
                    document_id=document_id,
                    chunk_index=start_index + index,
                    chunk_text=chunk,
                    chunk_metadata=chunk_metadata,
                )
                for index, chunk in enumerate(chunks)
            ]
            self.db.add_all(rows)
            self.db.flush()
            self.db.add_all(
                [
                    ChunkEmbeddings(
                        chunk_id=chunk.id,
                        provider_name=provider_name,
                        dimension=len(vector),
                        embedding=pad_embedding(vector),
                    )
                    for provider_name, vectors in embeddings_by_provider.items()
                    for chunk, vector in zip(rows, vectors, strict=True)
                ]
            )
            self.db.commit()

    def finish_staged_save(self, document_id: UUID, chunk_count: int) -> SavedDocument:
        with self._rollback_on_error("OCR 문서 저장을 완료하지 못했습니다."):
            document = self.db.get(AdminDocuments, document_id)
            if document is None:
                raise DocumentPersistenceError("저장 중인 OCR 문서를 찾을 수 없습니다.")
            document.ocr_status = "completed"
            self.db.commit()
            return SavedDocument(document_id=document_id, chunk_count=chunk_count)

    def abort_staged_save(self, document_id: UUID) -> None:
        with self._rollback_on_error("실패한 OCR 문서를 정리하지 못했습니다."):
            self.db.query(AdminDocuments).filter(AdminDocuments.id == document_id).delete()
            self.db.commit()
