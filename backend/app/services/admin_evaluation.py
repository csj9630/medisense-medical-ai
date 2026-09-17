"""관리자 페이지의 검색 정확도 지표 — `ai.evaluation.retrieval_eval`을 호출해서
Recall@k / MRR을 계산한다. 결과를 DB나 파일에 캐시하지 않는다 — 호출할 때마다
새로 계산한다(TODO: 매번 재계산이 느리면 캐싱 고려, ai/evaluation/CLAUDE.md 참고).
"""
import logging

from app.core.paths import PROJECT_ROOT
from app.schemas.admin import RetrievalEvalResponse

logger = logging.getLogger(__name__)

_EVAL_DATA_DIR = PROJECT_ROOT / "scripts" / "eval_data"
_CORPUS_PATH = _EVAL_DATA_DIR / "embedding_corpus.jsonl"
_QUERIES_PATH = _EVAL_DATA_DIR / "embedding_queries.jsonl"


class RetrievalEvalDatasetMissingError(Exception):
    """평가 데이터 파일(`scripts/eval_data/*.jsonl`)이 없을 때 발생합니다."""


class RetrievalEvalUnavailableError(Exception):
    """임베딩 모델을 로드하지 못하는 등 평가 자체를 실행할 수 없을 때 발생합니다."""


async def run_retrieval_evaluation() -> RetrievalEvalResponse:
    if not _CORPUS_PATH.exists() or not _QUERIES_PATH.exists():
        raise RetrievalEvalDatasetMissingError(
            f"평가 데이터가 없습니다: {_CORPUS_PATH.name}, {_QUERIES_PATH.name} "
            f"({_EVAL_DATA_DIR} 확인 필요)"
        )

    try:
        from ai.evaluation.retrieval_eval import evaluate_retrieval, load_eval_dataset
    except ImportError as exc:
        raise RetrievalEvalUnavailableError(
            "평가 모듈을 불러올 수 없습니다(ai/rag 의존성 미설치 등)."
        ) from exc

    corpus, queries = load_eval_dataset(str(_CORPUS_PATH), str(_QUERIES_PATH))
    logger.info("[RetrievalEval] 시작: corpus=%d queries=%d", len(corpus), len(queries))

    try:
        # CPU에서 corpus+query 임베딩을 계산하므로 시간이 걸릴 수 있다 — 이벤트 루프를
        # 막지 않도록 별도 스레드에서 돌린다.
        import asyncio

        result = await asyncio.to_thread(evaluate_retrieval, corpus, queries)
    except Exception as exc:
        logger.exception("[RetrievalEval] 실패")
        raise RetrievalEvalUnavailableError(f"평가 실행에 실패했습니다: {exc}") from exc

    logger.info("[RetrievalEval] 완료: mrr=%.4f", result.mrr)
    return RetrievalEvalResponse(
        num_queries=result.num_queries,
        recall_at_k={str(k): v for k, v in result.recall_at_k.items()},
        mrr=result.mrr,
        dataset_name=_CORPUS_PATH.stem,
    )
