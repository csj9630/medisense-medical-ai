"""RAG 데이터셋 ingestion에서 문서(admin_documents) 단위 CRUD만 담당한다. OCR
저장 경로(document_repository.py)는 문서+청크+임베딩을 한 트랜잭션으로 묶어서
처리하지만, ingestion은 idempotency 확인(문서가 이미 있는지 조회)이 먼저 필요해서
문서 생성만 별도로 뗀다.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.generated import AdminDocuments


class AdminDocumentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def find_by_original_file_url(self, url: str) -> AdminDocuments | None:
        return self.db.scalar(
            select(AdminDocuments).where(AdminDocuments.original_file_url == url)
        )

    def find_existing_urls(self, urls: list[str]) -> set[str]:
        """`urls` 중 이미 저장된 것만 골라 set으로 돌려준다. 대량 ingestion에서
        레코드마다 `find_by_original_file_url()`을 한 번씩 부르면(문서 수천~수만
        개면 그만큼 Neon 왕복이 생김) idempotency 확인 자체가 병목이 된다 -
        실제로 문서 50개에 임베딩 배치를 이미 붙였는데도 총 107초가 걸렸고,
        원인을 보니 idempotency 확인(레코드당 SELECT 1번)이 대부분이었다. 이
        메서드로 한 번의 IN 쿼리로 묶는다."""
        if not urls:
            return set()
        rows = self.db.scalars(
            select(AdminDocuments.original_file_url).where(
                AdminDocuments.original_file_url.in_(urls)
            )
        )
        return set(rows)

    def create(
        self, *, original_file_url: str, extracted_text: str, commit: bool = True
    ) -> AdminDocuments:
        # ocr_status="dataset_import"로 실제 OCR 업로드 문서("pending"/"completed")와
        # 구분한다 — 컬럼을 새로 추가하지 않고 기존 필드를 재사용.
        # commit=False: 대량 ingestion(rag_bulk_ingestion_service)이 여러 문서를
        # 묶어서 한 번에 커밋하기 위한 것 — flush만 해서 id는 채우되 트랜잭션은
        # 호출자가 끝낸다. 기존 단일 문서 호출부는 기본값(True)이라 동작 그대로.
        doc = AdminDocuments(
            original_file_url=original_file_url,
            ocr_extracted_text=extracted_text,
            ocr_status="dataset_import",
        )
        self.db.add(doc)
        if commit:
            self.db.commit()
            self.db.refresh(doc)
        else:
            # flush()가 PostgreSQL의 INSERT ... RETURNING으로 id를 이미 채워준다 -
            # 대량 처리에서 문서마다 refresh 왕복을 없애려고 commit=False일 때는
            # 생략한다(document_chunk.py의 create_chunks와 동일한 이유).
            self.db.flush()
        return doc
