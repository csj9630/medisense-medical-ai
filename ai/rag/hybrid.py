"""RRF(Reciprocal Rank Fusion) — 서로 다른 검색 결과의 순위만
가지고 점수를 합친다. 점수 스케일이 전혀 다른 방식의 원점수를
그대로 더하면 한쪽이 지배해버리는 문제를, 절대 점수 대신 '몇 등이었는지'만 써서 피한다."""

from collections.abc import Hashable
from typing import TypeVar

RankKey = TypeVar("RankKey", bound=Hashable)


def reciprocal_rank_fusion(
    ranked_lists: list[list[RankKey]],
    k: int = 60,
) -> list[tuple[RankKey, float]]:
    """각 검색 방식의 Chunk ID 순위를 RRF 점수 내림차순으로 반환합니다."""

    scores: dict[RankKey, float] = {}
    for ranked in ranked_lists:
        for rank, chunk_index in enumerate(ranked):
            scores[chunk_index] = scores.get(chunk_index, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)
