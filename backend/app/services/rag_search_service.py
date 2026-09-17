"""사용자 질의 → Neon(pgvector)에서 provider별로 검색 → RRF 결합 → (옵션) reranker.

`ai/rag/pipeline.retrieve()`와 같은 알고리즘이지만, 검색 대상이 메모리의 Chunk
리스트가 아니라 DB 테이블 전체라는 점이 다르다 — DB 세션이 필요해서 ai/rag 안에는
못 둔다(루트 CLAUDE.md 원칙).

임베딩 provider는 이 서비스를 호출하는 쪽(또는 모듈 기본값)이 정한다 — 팀원이 실제
모델을 확정하면 `search()`의 `providers=` 인자만 바꾸면 된다.
"""
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ai.rag import EmbeddingProvider, RemoteEmbeddingError, RetrievedChunk, hybrid
from ai.rag.reranker import rerank as rerank_candidates
from app.core.config import settings
from app.core.logging import get_logger
from app.core.rag_embedding import get_default_rag_embedding_providers
from app.models.generated import DocumentChunks
from app.repositories.document_chunk import DocumentChunkRepository

logger = get_logger("services.rag_search")

# 최종 top_k보다 넉넉히 뽑아서 RRF/reranker 후보 풀을 만든다 — 최소 후보 수는
# EMBEDDING_SEARCH_CANDIDATES로 조정 가능(config.py 참고).
_CANDIDATE_MULTIPLIER = 4

# 진료과/신뢰도 소프트 부스트 — ai/rag/CLAUDE.md TODO("진료과 분류 결과를 검색
# 필터로 쓸지: 강제 필터 vs soft filter")에 대한 답. 강제 필터(불일치하면 후보에서
# 아예 제외)로 만들지 않은 이유: 분류기(ai/consultation/classifier.py)가 키워드
# 매칭이라 오탐할 수 있는데, 강제 필터였다면 오탐 시 정답 청크가 후보에서 완전히
# 사라진다. 곱연산 소프트 부스트는 최악의 경우(분류가 틀림)에도 순수 RRF 결과와
# 크게 다르지 않으면서, 맞을 때만 관련 청크를 끌어올린다. `ai/rag` 패키지 자체가
# 아니라 이 서비스(backend/app)에 둔 이유도 같은 문서 참고 — ai/rag는 진료과
# 개념을 몰라야 한다.
#
# 진료과 부스트: 2026-09-02 기준 department 메타데이터를 실제로 채우는 어댑터는
# snuh_clinical_qa 하나뿐이다(ai/rag/ingestion/adapters/*.py 확인 — 나머지는
# 빈 리스트). 그래서 지금은 효과 범위가 작지만, 다른 어댑터도 나중에 department를
# 채우면 코드 변경 없이 자동으로 넓어진다.
_DEPARTMENT_MATCH_BOOST = 1.2

# 신뢰도(source_tier) 부스트 — 1=공식기관 원문, 2=전문가 검수, 3=AI 생성(검수
# 없음), 4=번역+검수 없음(모든 어댑터가 채우므로 코퍼스 전체에 바로 적용됨,
# ai/rag/ingestion/adapters/*.py 참고). 값이 없거나 알 수 없는 tier는 부스트도
# 페널티도 주지 않는다(1.0).
_SOURCE_TIER_BOOST = {1: 1.15, 2: 1.08, 3: 1.0, 4: 0.95}


def _boost_multiplier(metadata: dict | None, department: str | None) -> float:
    metadata = metadata or {}
    multiplier = _SOURCE_TIER_BOOST.get(metadata.get("source_tier"), 1.0)
    if department and department in (metadata.get("department") or []):
        multiplier *= _DEPARTMENT_MATCH_BOOST
    return multiplier


def _apply_soft_boosts(
    fused: list[tuple[UUID, float]],
    rows_by_id: dict[UUID, DocumentChunks],
    department: str | None,
) -> list[tuple[UUID, float]]:
    # getattr로 방어하는 이유: 테스트 stub(SimpleNamespace)처럼 chunk_metadata
    # 속성이 아예 없는 객체가 와도(실제 ORM 행은 항상 있음, 값이 None일 뿐) 깨지면
    # 안 된다 — pipeline.py의 execution/result 필드 방어와 같은 원칙.
    boosted = [
        (chunk_id, score * _boost_multiplier(getattr(rows_by_id[chunk_id], "chunk_metadata", None), department))
        for chunk_id, score in fused
    ]
    return sorted(boosted, key=lambda item: item[1], reverse=True)


def search(
    db: Session,
    query: str,
    top_k: int = 5,
    use_reranker: bool = False,
    providers: list[EmbeddingProvider] | None = None,
    department: str | None = None,
) -> list[RetrievedChunk]:
    """`department`: 호출하는 쪽(message.py)이 ai.consultation.classifier로 미리
    분류해서 넘긴 진료과 이름(예: "정형외과"). RRF 결합 직후 청크 메타데이터의
    `department`/`source_tier`에 따라 점수를 소프트 부스트하는 데만 쓴다 —
    안 넘기면(None) 신뢰도 부스트만 적용되고 진료과 부스트는 걸리지 않는다."""
    if not query.strip():
        return []

    providers = providers or get_default_rag_embedding_providers()
    candidate_k = max(top_k * _CANDIDATE_MULTIPLIER, settings.embedding_search_candidates)
    repo = DocumentChunkRepository(db)

    rows_by_id: dict[UUID, DocumentChunks] = {}
    ranked_lists: list[list[UUID]] = []

    for provider in providers:
        try:
            query_vector = provider.embed_query(query)
        except RemoteEmbeddingError as exc:
            # 원격 임베딩 서버(Vast.ai 등) 연결 실패는 알 수 없는 내부 버그가
            # 아니라 이미 원인이 밝혀진 외부 의존성 장애다 — router의 범용
            # except Exception이 500으로 뭉개기 전에 여기서 503으로 구분해서
            # 클라이언트/모니터링이 "재시도하면 될 수 있는 문제"로 알 수 있게 한다.
            logger.warning("rag_search: 임베딩 provider=%s 연결 실패: %s", provider.name, exc)
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
        hits = repo.search_by_provider(provider.name, query_vector, candidate_k)
        ranked_lists.append([chunk.id for chunk, _distance in hits])
        for chunk, _distance in hits:
            rows_by_id[chunk.id] = chunk

    if not rows_by_id:
        logger.warning("rag_search: 검색 결과 없음 (모든 provider 0건) query=%r", query)
        return []

    fused = hybrid.reciprocal_rank_fusion(ranked_lists, k=settings.embedding_rrf_k)
    fused = _apply_soft_boosts(fused, rows_by_id, department)

    if use_reranker and fused:
        candidate_ids = [chunk_id for chunk_id, _ in fused[: max(top_k * 3, top_k)]]
        candidate_texts = [rows_by_id[cid].chunk_text for cid in candidate_ids]
        reranked = rerank_candidates(query, candidate_texts)
        ordered = [(candidate_ids[i], score) for i, score in reranked]
    else:
        ordered = fused

    results: list[RetrievedChunk] = []
    for position, (chunk_id, score) in enumerate(ordered[:top_k]):
        row = rows_by_id[chunk_id]
        metadata = getattr(row, "chunk_metadata", None) or {}
        results.append(
            RetrievedChunk(
                index=position,
                text=row.chunk_text,
                score=float(score),
                chunk_id=str(row.id),
                document_id=str(row.document_id),
                # ingestion 때 이미 채워둔 metadata(source/source_tier/department/
                # disease/symptoms/reliability/verification_status)를 그대로
                # 넘긴다 - 이전엔 여기서 안 넘겨서 build_reference_info_block()의
                # 출처 표시 로직이 항상 source=None만 받는 죽은 코드였다.
                source=metadata.get("source"),
                metadata=metadata,
            )
        )
    return results
