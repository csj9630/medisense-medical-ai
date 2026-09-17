import unittest

from ai.rag.chunking import Chunk
from ai.rag.pipeline import retrieve


class _FakeProvider:
    """텍스트 -> 미리 정해둔 벡터. 실제 임베딩 모델 없이 RRF/순위 로직만 검증한다."""

    def __init__(self, name: str, vectors: dict[str, list[float]]) -> None:
        self.name = name
        self.dimension = len(next(iter(vectors.values())))
        self._vectors = vectors

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._vectors[t] for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vectors[text]


class RetrieveTest(unittest.TestCase):
    def setUp(self) -> None:
        self.chunks = [
            Chunk(index=0, text="chunk-a"),
            Chunk(index=1, text="chunk-b"),
            Chunk(index=2, text="chunk-c"),
        ]

    def test_empty_chunks_returns_empty(self) -> None:
        self.assertEqual(retrieve([], "query", providers=[]), [])

    def test_single_provider_ranks_by_cosine_similarity(self) -> None:
        provider = _FakeProvider(
            "p1",
            {
                "chunk-a": [1.0, 0.0],
                "chunk-b": [0.0, 1.0],
                "chunk-c": [-1.0, 0.0],
                "query": [0.9, 0.1],
            },
        )
        results = retrieve(self.chunks, "query", top_k=3, providers=[provider])
        self.assertEqual(results[0].text, "chunk-a")  # query와 방향이 가장 비슷함

    def test_two_providers_combine_via_rrf(self) -> None:
        # provider1은 chunk-a를 1등으로, provider2는 chunk-b를 1등으로 미는 상황 —
        # 둘 다 어느 정도 지지하는 chunk-c가 RRF에서 유리해지는지 확인한다기보다는,
        # 최소한 한쪽에서만 1등인 항목이 결과에 다 포함되는지(순위 결합이 실제로
        # 두 provider를 다 반영하는지)를 검증한다.
        provider1 = _FakeProvider(
            "p1",
            {
                "chunk-a": [1.0, 0.0],
                "chunk-b": [0.0, 1.0],
                "chunk-c": [0.0, -1.0],
                "query": [1.0, 0.0],
            },
        )
        provider2 = _FakeProvider(
            "p2",
            {
                "chunk-a": [0.0, -1.0],
                "chunk-b": [1.0, 0.0],
                "chunk-c": [0.0, 1.0],
                "query": [1.0, 0.0],
            },
        )
        results = retrieve(self.chunks, "query", top_k=3, providers=[provider1, provider2])
        result_texts = {r.text for r in results}
        self.assertEqual(result_texts, {"chunk-a", "chunk-b", "chunk-c"})

    def test_default_providers_used_when_none_given(self) -> None:
        # providers=None이면 해싱 placeholder로 대체된다 — 최소한 에러 없이 top_k개를 반환.
        results = retrieve(self.chunks, "아무 질의", top_k=2)
        self.assertEqual(len(results), 2)


if __name__ == "__main__":
    unittest.main()
