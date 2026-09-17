import unittest

from ai.evaluation.retrieval_eval import CorpusDoc, EvalQuery, evaluate_retrieval

# 텍스트 문자열 -> 미리 정한 벡터. 실제 임베딩 모델을 안 띄우고 순위 로직만 검증한다.
_FAKE_VECTORS = {
    "doc-a": [1.0, 0.0, 0.0],
    "doc-b": [0.0, 1.0, 0.0],
    "doc-c": [0.0, 0.0, 1.0],
    "query-a": [0.9, 0.1, 0.0],  # doc-a와 가장 가까움
    "query-b": [0.1, 0.9, 0.0],  # doc-b와 가장 가까움
    "query-miss": [0.0, 0.0, 0.0],  # 아무것도 강하게 안 가까움 -> 순위 낮음
}


class _FakeProvider:
    name = "fake"
    dimension = 3

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [_FAKE_VECTORS[text] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return _FAKE_VECTORS[text]


class EvaluateRetrievalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.corpus = [
            CorpusDoc(id="a", text="doc-a"),
            CorpusDoc(id="b", text="doc-b"),
            CorpusDoc(id="c", text="doc-c"),
        ]
        self.provider = _FakeProvider()

    def test_empty_inputs_return_zero_without_calling_embeddings(self) -> None:
        result = evaluate_retrieval([], [])
        self.assertEqual(result.num_queries, 0)
        self.assertEqual(result.mrr, 0.0)

    def test_perfect_top1_match_gives_recall_1_and_mrr_1(self) -> None:
        queries = [EvalQuery(query="query-a", relevant_id="a"), EvalQuery(query="query-b", relevant_id="b")]

        result = evaluate_retrieval(self.corpus, queries, k_values=(1, 3), provider=self.provider)

        self.assertEqual(result.num_queries, 2)
        self.assertEqual(result.recall_at_k[1], 1.0)
        self.assertEqual(result.mrr, 1.0)

    def test_missed_query_lowers_recall_at_1_but_not_recall_at_k_covering_all(self) -> None:
        queries = [EvalQuery(query="query-miss", relevant_id="a")]

        result = evaluate_retrieval(self.corpus, queries, k_values=(1, 3), provider=self.provider)

        # corpus가 3개뿐이라 k=3이면(=corpus 전체) 무조건 recall 1.0이어야 한다.
        self.assertEqual(result.recall_at_k[3], 1.0)


if __name__ == "__main__":
    unittest.main()
