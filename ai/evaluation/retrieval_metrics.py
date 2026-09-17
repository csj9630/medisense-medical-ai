"""검색 품질 지표 — Recall@k, Precision@k, MRR, nDCG@k. 임베딩/하이브리드 검색
비교에 공통으로 쓴다.

지금 있는 평가셋은 문서(질문)당 정답 chunk가 하나뿐인 binary relevance라서
(scripts/build_retrieval_benchmark.py 참고 — 등급 relevance 라벨은 아직 없음),
nDCG의 IDCG(이상적인 경우의 DCG)는 항상 "정답이 1등일 때"인 1/log2(2)=1.0으로
고정된다 — 그래서 DCG를 IDCG로 나누는 정규화 없이 DCG 값 자체가 곧 nDCG다.
나중에 등급 relevance(0/1/2)가 생기면 이 단순화는 안 맞으니 다시 봐야 한다.
"""
import math


def recall_at_k(ranked_ids: list[str], relevant_id: str, k: int) -> int:
    """ranked_ids 상위 k개 안에 relevant_id가 있으면 1, 없으면 0. 정답이 하나뿐인
    지금 평가셋 구조에서는 Hit@k와 값이 같다(사실상 별칭)."""
    return 1 if relevant_id in ranked_ids[:k] else 0


def precision_at_k(ranked_ids: list[str], relevant_id: str, k: int) -> float:
    """상위 k개 중 관련 문서 비율. 정답이 하나뿐이므로 맞혔으면 1/k, 못 맞혔으면 0."""
    if k <= 0:
        return 0.0
    return (1.0 / k) if relevant_id in ranked_ids[:k] else 0.0


def reciprocal_rank(ranked_ids: list[str], relevant_id: str) -> float:
    """relevant_id의 순위 역수(1위=1.0, 2위=0.5, ...). 못 찾으면 0."""
    if relevant_id in ranked_ids:
        return 1.0 / (ranked_ids.index(relevant_id) + 1)
    return 0.0


def ndcg_at_k(ranked_ids: list[str], relevant_id: str, k: int) -> float:
    """단일 정답 문서 기준 nDCG@k. relevant_id가 상위 k 안에서 순위 r(1-indexed)에
    있으면 1/log2(r+1), 없으면 0 - MRR과 달리 순위가 뒤로 갈수록 점수가 더 가파르게
    깎인다(로그 감쇠)."""
    if relevant_id in ranked_ids[:k]:
        rank = ranked_ids.index(relevant_id) + 1
        return 1.0 / math.log2(rank + 1)
    return 0.0
