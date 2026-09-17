"""Cross-encoder reranker — dragonkue/bge-reranker-v2-m3-ko (한국어 벤치마크 상위권).
1차 검색 후보(RRF 결합 결과)를 질문과 다시 쌍으로 넣어 정밀하게 재정렬한다.

후보 하나하나마다 모델을 다시 돌려야 해서(cross-encoder) dense/keyword 검색보다
훨씬 비싸다 — 리소스 제약 환경(무료 티어 배포 등)에서는 끄고 RRF 결과를 그대로
쓰도록 pipeline.py의 use_reranker 플래그로 켜고 끌 수 있게 했다."""
from functools import lru_cache

RERANKER_MODEL_NAME = "dragonkue/bge-reranker-v2-m3-ko"


@lru_cache(maxsize=1)
def _get_reranker():
    from sentence_transformers import CrossEncoder

    return CrossEncoder(RERANKER_MODEL_NAME)


def rerank(query: str, candidates: list[str]) -> list[tuple[int, float]]:
    """candidates: 후보 청크 텍스트 리스트. 반환: (candidates 안에서의 인덱스, 점수) 점수 내림차순."""
    if not candidates:
        return []
    model = _get_reranker()
    scores = model.predict([(query, c) for c in candidates])
    ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)
    return [(i, float(s)) for i, s in ranked]
