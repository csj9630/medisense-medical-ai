import math
import unittest

from ai.evaluation.retrieval_metrics import (
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


class RecallAtKTest(unittest.TestCase):
    def test_hit_within_k(self) -> None:
        self.assertEqual(recall_at_k(["a", "b", "c"], "b", k=2), 1)

    def test_miss_outside_k(self) -> None:
        self.assertEqual(recall_at_k(["a", "b", "c"], "c", k=2), 0)

    def test_not_found_at_all(self) -> None:
        self.assertEqual(recall_at_k(["a", "b"], "z", k=5), 0)


class PrecisionAtKTest(unittest.TestCase):
    def test_hit_gives_one_over_k(self) -> None:
        self.assertAlmostEqual(precision_at_k(["a", "b", "c"], "b", k=3), 1 / 3)

    def test_miss_gives_zero(self) -> None:
        self.assertEqual(precision_at_k(["a", "b"], "z", k=3), 0.0)

    def test_zero_k_is_zero_not_division_error(self) -> None:
        self.assertEqual(precision_at_k(["a"], "a", k=0), 0.0)


class ReciprocalRankTest(unittest.TestCase):
    def test_first_place(self) -> None:
        self.assertEqual(reciprocal_rank(["a", "b"], "a"), 1.0)

    def test_second_place(self) -> None:
        self.assertEqual(reciprocal_rank(["a", "b"], "b"), 0.5)

    def test_not_found(self) -> None:
        self.assertEqual(reciprocal_rank(["a", "b"], "z"), 0.0)


class NdcgAtKTest(unittest.TestCase):
    def test_first_place_scores_one(self) -> None:
        # 1등이면 1/log2(2) = 1.0
        self.assertEqual(ndcg_at_k(["a", "b", "c"], "a", k=3), 1.0)

    def test_second_place_scores_less_than_first(self) -> None:
        score = ndcg_at_k(["a", "b", "c"], "b", k=3)
        self.assertAlmostEqual(score, 1.0 / math.log2(3))
        self.assertLess(score, 1.0)

    def test_decays_faster_than_reciprocal_rank_at_later_ranks(self) -> None:
        # nDCG는 로그 감쇠라 MRR(1/rank)보다 뒤쪽 순위에서 덜 가혹해야 한다 -
        # 두 지표가 서로 다른 정보를 준다는 걸 확인(같은 값이면 nDCG를 따로 둘 이유가 없음).
        ranked = ["a", "b", "c", "d", "e"]
        ndcg = ndcg_at_k(ranked, "e", k=5)
        mrr = reciprocal_rank(ranked, "e")
        self.assertGreater(ndcg, mrr)

    def test_miss_outside_k_scores_zero(self) -> None:
        self.assertEqual(ndcg_at_k(["a", "b", "c"], "d", k=2), 0.0)


if __name__ == "__main__":
    unittest.main()
