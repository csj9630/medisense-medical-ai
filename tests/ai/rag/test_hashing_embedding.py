import unittest

import numpy as np

from ai.rag.embeddings.hashing import HashingEmbeddingProvider


class HashingEmbeddingProviderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = HashingEmbeddingProvider(dimension=64)

    def test_dimension_matches_configured_value(self) -> None:
        vector = self.provider.embed_query("아무 텍스트")
        self.assertEqual(len(vector), 64)

    def test_deterministic_across_calls(self) -> None:
        # DB에 저장한 벡터와 나중에 다시 계산한 쿼리 벡터가 같은 규칙으로 나와야 하므로
        # 결정론적이어야 한다 — Python의 hash()는 프로세스마다 랜덤이라 이게 안 됨.
        first = self.provider.embed_query("두통이 심해요")
        second = self.provider.embed_query("두통이 심해요")
        self.assertEqual(first, second)

    def test_is_unit_normalized(self) -> None:
        vector = np.array(self.provider.embed_query("어지럼증과 구토 증상"))
        self.assertAlmostEqual(float(np.linalg.norm(vector)), 1.0, places=5)

    def test_shared_words_are_more_similar_than_unrelated_text(self) -> None:
        base = np.array(self.provider.embed_query("두통과 어지럼증이 있어요"))
        similar = np.array(self.provider.embed_query("두통과 구토 증상이 있어요"))
        unrelated = np.array(self.provider.embed_query("발목을 삐끗했어요"))

        self.assertGreater(float(base @ similar), float(base @ unrelated))

    def test_empty_text_returns_zero_vector_without_error(self) -> None:
        vector = self.provider.embed_query("")
        self.assertEqual(vector, [0.0] * 64)


if __name__ == "__main__":
    unittest.main()
