from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.generated import AdminDocuments, ChunkEmbeddings, DocumentChunks

# 마이그레이션(a1f3c9d2e8b4)의 chunk_embeddings.embedding VECTOR 폭과 반드시 같아야 한다.
# 원래 03b8a4b5b62a가 2048로 넓게 잡았던 건 향후 더 큰 임베딩 모델 대비였는데,
# 실제 확정된 Jina v4/Medical BGE-M3가 둘 다 1024차원이라 절반이 0-padding으로
# 낭비되고 있었다(실제 DB에서 전체 용량의 42%로 확인됨) - 1024로 좁혔다.
EMBEDDING_COLUMN_WIDTH = 1024


def pad_embedding(vector: list[float]) -> list[float]:
    """모든 provider의 벡터를 같은 폭의 컬럼에 저장하기 위해 0으로 채운다 — 코사인
    유사도는 두 벡터를 같은 자리만큼 0으로 패딩해도 값이 바뀌지 않는다(내적/노름
    둘 다 0 기여)."""
    if len(vector) > EMBEDDING_COLUMN_WIDTH:
        raise ValueError(
            f"임베딩 차원({len(vector)})이 컬럼 폭({EMBEDDING_COLUMN_WIDTH})을 초과합니다 — "
            "마이그레이션의 EMBEDDING_COLUMN_WIDTH를 늘리거나 Matryoshka 등으로 축소하세요."
        )
    return vector + [0.0] * (EMBEDDING_COLUMN_WIDTH - len(vector))


class DocumentChunkRepository:
    """document_chunks / chunk_embeddings 저장·검색만 담당한다. 임베딩 계산(ai.rag)과
    RRF 결합은 상위 서비스 계층의 책임."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_chunks(
        self,
        document_id: UUID,
        rows: list[dict],
        *,
        metadata: dict | None = None,
        commit: bool = True,
    ) -> list[DocumentChunks]:
        """rows: {chunk_index, chunk_text} 딕셔너리 리스트. 임베딩은 별도로
        `add_embeddings()`를 호출해서 붙인다. metadata는 문서 전체 청크에 동일하게
        적용된다(RAG 데이터셋 ingestion에서 출처/진료과/신뢰도 등을 추적하기 위함) —
        생략하면 NULL이라 기존 OCR 저장 경로는 그대로 동작한다.
        commit=False: 대량 ingestion이 여러 문서의 청크를 모아서 한 번에 커밋하기
        위한 것 — flush만 해서 id는 채우되 트랜잭션은 호출자가 끝낸다.

        commit=False일 때는 청크별 refresh()를 안 한다 - PostgreSQL은 INSERT에
        RETURNING을 붙여서 서버 생성 기본값(id)을 flush() 시점에 이미 채워주므로
        refresh()는 원래도 불필요한 왕복이었다. 다만 기존 단일 문서 경로(commit=True,
        청크 2~5개라 비용이 작음)는 동작을 안 바꾸려고 그대로 뒀다 - 대량 처리에서만
        문서당 청크 수십~수백 개가 전부 refresh 왕복을 만들어 실제로 체감될 만큼
        느려졌던 걸 확인하고 여기만 없앴다."""
        chunks = [
            DocumentChunks(document_id=document_id, chunk_metadata=metadata, **row) for row in rows
        ]
        self.db.add_all(chunks)
        if commit:
            self.db.commit()
            for chunk in chunks:
                self.db.refresh(chunk)
        else:
            self.db.flush()
        return chunks

    def add_embeddings(
        self,
        chunk_id: UUID,
        provider_name: str,
        dimension: int,
        vector: list[float],
        *,
        commit: bool = True,
    ) -> None:
        self.db.add(
            ChunkEmbeddings(
                chunk_id=chunk_id,
                provider_name=provider_name,
                dimension=dimension,
                embedding=pad_embedding(vector),
            )
        )
        if commit:
            self.db.commit()

    def delete_by_document(self, document_id: UUID) -> None:
        """재수집(re-ingest) 전에 같은 문서의 기존 청크를 지운다 — chunk_embeddings는
        ON DELETE CASCADE라 같이 지워진다."""
        self.db.query(DocumentChunks).filter(DocumentChunks.document_id == document_id).delete()
        self.db.commit()

    def search_by_provider(
        self, provider_name: str, query_vector: list[float], top_k: int
    ) -> list[tuple[DocumentChunks, float]]:
        """지정한 provider로 저장된 임베딩만 대상으로 코사인 거리 기준 상위 top_k를
        반환한다. 반환값은 (청크, 코사인_거리) — 거리가 작을수록 더 유사하다.

        `admin_documents.ocr_status`가 "completed"(관리자가 텍스트/ZIP/웹URL로
        업로드해서 처리 완료한 문서) 또는 "dataset_import"(HuggingFace 데이터셋
        대량 RAG 적재)인 문서의 청크만 대상으로 한다 - `document_chunks`/
        `chunk_embeddings`는 이 둘과, 그 사이 상태(OCR "pending"/"processing" -
        아직 처리 중이라 검색에 노출되면 안 됨)까지 같이 쓰는 테이블이다.
        "completed"만 필터링하던 이전 버전은 dataset_import 청크(전체 RAG
        코퍼스)를 몽땅 걸러버리는 버그가 있었고, source metadata 유무로 걸러내던
        버전은 관리자 업로드 청크(metadata를 안 채움)를 몽땅 걸러버리는 버그가
        있었다 - 실제 라이브 쿼리로 두 버그 다 재현해서 확인 후 이 형태로 합쳤다
        (2026-09-03). 개발자가 테스트 삼아 올렸다가 저장까지 눌러버린 문서(2026-08
        중 6건 발견 후 삭제함)처럼, "completed"긴 한데 RAG용으로 의도한 콘텐츠가
        아닌 경우는 이 필터로 못 거른다 - 그런 문서가 다시 쌓이면 코드가 아니라
        데이터를 지워서 정리해야 한다(admin_documents에 "이건 RAG용으로 큐레이션한
        문서다"를 표시하는 컬럼이 아직 없음 - 후속 과제)."""
        padded_query = pad_embedding(query_vector)
        stmt = (
            select(DocumentChunks, ChunkEmbeddings.embedding.cosine_distance(padded_query).label("distance"))
            .join(ChunkEmbeddings, ChunkEmbeddings.chunk_id == DocumentChunks.id)
            .join(AdminDocuments, AdminDocuments.id == DocumentChunks.document_id)
            .where(
                ChunkEmbeddings.provider_name == provider_name,
                AdminDocuments.ocr_status.in_(("completed", "dataset_import")),
            )
            .order_by("distance")
            .limit(top_k)
        )
        return [(row.DocumentChunks, row.distance) for row in self.db.execute(stmt)]

    def get_by_ids(self, chunk_ids: list[UUID]) -> dict[UUID, DocumentChunks]:
        stmt = select(DocumentChunks).where(DocumentChunks.id.in_(chunk_ids))
        return {row.id: row for row in self.db.scalars(stmt)}

    def find_existing_chunk_texts(self, texts: list[str]) -> set[str]:
        """이미 document_chunks에 완전히 같은 텍스트로 저장된 청크가 있는지
        확인한다(출처 무관 - HF/KDCA 데이터셋이든 다른 관리자 업로드든 전부
        대상). ai/rag/ingestion의 Deduplicator(content_hash 기반)와 목적은
        같지만, 그건 배치 스크립트 실행 하나 안에서만 유효한 파일 기반
        스냅샷이라 실시간 웹 요청(동시 업로드 가능)에 그대로 쓸 수 없다 -
        여기서는 매 요청마다 실제 DB에 직접 물어봐서 항상 최신 상태를 반영하고,
        여러 관리자가 동시에 올려도 (매 요청이 독립적인 SELECT라) 파일 락 같은
        동시성 문제가 없다. 해시 컬럼을 새로 안 만들고 chunk_text 전체를 그대로
        비교하는 이유: 한 번에 비교하는 개수가 업로드 문서 하나 분량(수십~수백
        개)이라 스캔 비용이 크지 않고, 스키마 변경 없이 바로 적용할 수 있다."""
        if not texts:
            return set()
        stmt = select(DocumentChunks.chunk_text).where(DocumentChunks.chunk_text.in_(texts))
        return set(self.db.scalars(stmt))
