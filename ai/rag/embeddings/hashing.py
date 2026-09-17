"""팀원이 실제 임베딩 모델(들)을 확정하기 전까지, RAG 파이프라인 전체(청킹→벡터화→
저장→검색→RRF)를 GPU/네트워크 없이 바로 돌려볼 수 있게 하는 결정론적 가짜 임베딩.

의미 기반 검색 품질은 전혀 없다(그냥 텍스트를 숫자로 바꾼 것) — "같은 단어를 많이
공유하는 텍스트가 비슷한 벡터가 된다" 정도만 보장한다. 실제 검색 정확도를 보려는
용도가 아니라, 배관(pipeline/DB 저장/API) 자체가 끝까지 동작하는지 확인하는 용도다.
팀원이 실제 모델을 정하면 `EmbeddingProvider`만 새로 구현해서 갈아끼우면 된다.
"""
import hashlib
import re

import numpy as np

_TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text.lower())


def _stable_hash(token: str, salt: str = "") -> int:
    # hash()는 프로세스마다 랜덤 시드가 달라 재현이 안 되므로(문자열 해시 랜덤화),
    # 항상 같은 값이 나오는 hashlib을 쓴다 — DB에 저장한 벡터와 나중에 다시 계산한
    # 쿼리 벡터가 같은 규칙으로 만들어져야 하기 때문에 결정론적이어야 한다.
    digest = hashlib.sha256(f"{salt}:{token}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


class HashingEmbeddingProvider:
    """Feature hashing(해싱 트릭) 기반 임베딩. `dimension`을 넓게 잡을수록 서로 다른
    단어끼리 같은 버킷에 부딪히는(collision) 빈도가 줄어든다."""

    name = "hashing-placeholder"

    def __init__(self, dimension: int = 512) -> None:
        self.dimension = dimension

    def _embed_one(self, text: str) -> list[float]:
        vector = np.zeros(self.dimension, dtype=np.float64)
        for token in _tokenize(text):
            bucket = _stable_hash(token) % self.dimension
            sign = 1.0 if _stable_hash(token, salt="sign") % 2 == 0 else -1.0
            vector[bucket] += sign

        norm = np.linalg.norm(vector)
        if norm == 0:
            # 빈 텍스트/전부 걸러진 텍스트 — 영벡터를 그대로 두면 나중에 코사인
            # 유사도 계산(내적)에서 이 항목만 항상 0이 되어 안전하게 순위 맨 뒤로 감.
            return vector.tolist()
        return (vector / norm).tolist()

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)
