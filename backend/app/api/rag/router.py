from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth.dependencies import get_current_user
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.generated import Users
from app.schemas.rag import RagSearchRequest, RagSearchResponse, RagSearchResultItem
from app.services.rag_search_service import search as rag_search

router = APIRouter()
logger = get_logger("api.rag")


@router.post("/search", response_model=RagSearchResponse)
def search_documents(
    payload: RagSearchRequest,
    current_user: Annotated[Users, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> RagSearchResponse:
    """Neon(pgvector)에 저장된 문서 청크를 검색한다. 지금은 임베딩 모델이 아직 안
    정해져서(팀원 진행 중) 자리 채우기용 해싱 임베딩으로 동작한다 — 검색 결과의
    의미적 정확도는 보장하지 않는다. 실제 모델이 정해지면 provider만 교체된다."""
    if not payload.query.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "검색어를 입력해주세요.")

    try:
        results = rag_search(
            db, payload.query, top_k=payload.top_k, use_reranker=payload.use_reranker
        )
    except HTTPException:
        # rag_search_service가 이미 원인을 구분해서 던진 의도된 오류(예: 원격
        # 임베딩 서버 연결 실패 → 503)는 그대로 통과시킨다 — 아래 except
        # Exception이 "알 수 없는 내부 오류"로 뭉개면 원인 정보가 사라진다.
        raise
    except Exception as exc:
        logger.exception("RAG 검색 중 오류: query=%r", payload.query)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "검색에 실패했습니다.") from exc

    return RagSearchResponse(
        query=payload.query,
        results=[
            RagSearchResultItem(
                chunk_id=r.chunk_id,
                document_id=r.document_id,
                content=r.text,
                score=r.score,
            )
            for r in results
        ],
    )
