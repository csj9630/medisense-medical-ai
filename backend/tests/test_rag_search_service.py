import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ai.rag import RemoteEmbeddingError
from app.core.config import settings
from app.services.rag_search_service import search


class RagSearchServiceTest(unittest.TestCase):
    def test_jina_and_bge_rankings_are_combined_by_chunk_uuid(self) -> None:
        document_id = uuid4()
        chunk_a = _chunk(document_id, "A")
        chunk_b = _chunk(document_id, "B")
        chunk_c = _chunk(document_id, "C")
        repository = FakeRepository(
            {
                "jina-v4": [chunk_a, chunk_b, chunk_c],
                "medical-bgem3": [chunk_b, chunk_c, chunk_a],
            }
        )

        with patch(
            "app.services.rag_search_service.DocumentChunkRepository",
            return_value=repository,
        ):
            results = search(
                Mock(spec=Session),
                "폐렴 증상",
                top_k=3,
                providers=[
                    FakeProvider("jina-v4", 0.1),
                    FakeProvider("medical-bgem3", 0.2),
                ],
            )

        self.assertEqual([result.text for result in results], ["B", "A", "C"])
        self.assertEqual(repository.requested_limits, [20, 20])
        self.assertEqual(repository.query_heads, [0.1, 0.2])

    def test_search_candidate_count_follows_setting(self) -> None:
        # EMBEDDING_SEARCH_CANDIDATES는 예전엔 코드에 하드코딩된 상수였다 — 설정으로
        # 뺀 뒤에도 실제로 반영되는지 확인.
        repository = FakeRepository({"jina-v4": [_chunk(uuid4(), "A")]})

        with (
            patch("app.services.rag_search_service.DocumentChunkRepository", return_value=repository),
            patch.object(settings, "embedding_search_candidates", 5),
        ):
            search(Mock(spec=Session), "질문", top_k=1, providers=[FakeProvider("jina-v4", 0.1)])

        self.assertEqual(repository.requested_limits, [5])

    def test_rrf_k_follows_setting(self) -> None:
        chunk_a, chunk_b = _chunk(uuid4(), "A"), _chunk(uuid4(), "B")
        repository = FakeRepository(
            {"jina-v4": [chunk_a, chunk_b], "medical-bgem3": [chunk_b, chunk_a]}
        )

        with (
            patch("app.services.rag_search_service.DocumentChunkRepository", return_value=repository),
            patch("app.services.rag_search_service.hybrid.reciprocal_rank_fusion") as mock_rrf,
        ):
            mock_rrf.return_value = [(chunk_a.id, 1.0)]
            with patch.object(settings, "embedding_rrf_k", 5):
                search(
                    Mock(spec=Session),
                    "질문",
                    top_k=1,
                    providers=[FakeProvider("jina-v4", 0.1), FakeProvider("medical-bgem3", 0.2)],
                )

        self.assertEqual(mock_rrf.call_args.kwargs.get("k"), 5)

    def test_remote_embedding_failure_raises_503_not_generic_500(self) -> None:
        # 2026-09-08: 원격 임베딩 서버(Vast.ai) 연결 실패가 router의 범용
        # except Exception에 잡혀 500 "검색에 실패했습니다"로 뭉개지던 버그.
        # 원인이 이미 밝혀진 외부 의존성 장애이므로 503으로 구분돼야 한다.
        repository = FakeRepository({"jina-v4": []})

        with patch(
            "app.services.rag_search_service.DocumentChunkRepository",
            return_value=repository,
        ):
            with self.assertRaises(HTTPException) as ctx:
                search(
                    Mock(spec=Session),
                    "질문",
                    top_k=1,
                    providers=[FailingProvider("jina-v4")],
                )

        self.assertEqual(ctx.exception.status_code, 503)


class RetrievedChunkMetadataForwardingTest(unittest.TestCase):
    """RetrievedChunk에 source/metadata를 안 채워서 build_reference_info_block()의
    출처 표시 로직이 항상 죽은 코드였던 버그(2026-09-02) - 이제 chunk_metadata를
    그대로 넘기는지 확인."""

    def test_source_and_metadata_are_populated_from_chunk_metadata(self) -> None:
        document_id = uuid4()
        chunk = _chunk(
            document_id,
            "A",
            chunk_metadata={"source": "Asan-AMC-Healthinfo", "source_tier": 1, "department": ["정형외과"]},
        )
        repository = FakeRepository({"jina-v4": [chunk]})

        with patch(
            "app.services.rag_search_service.DocumentChunkRepository",
            return_value=repository,
        ):
            results = search(
                Mock(spec=Session), "질문", top_k=1, providers=[FakeProvider("jina-v4", 0.1)]
            )

        self.assertEqual(results[0].source, "Asan-AMC-Healthinfo")
        self.assertEqual(results[0].metadata, {"source": "Asan-AMC-Healthinfo", "source_tier": 1, "department": ["정형외과"]})

    def test_missing_chunk_metadata_leaves_source_none_without_crashing(self) -> None:
        document_id = uuid4()
        chunk = _chunk(document_id, "A", chunk_metadata=None)
        repository = FakeRepository({"jina-v4": [chunk]})

        with patch(
            "app.services.rag_search_service.DocumentChunkRepository",
            return_value=repository,
        ):
            results = search(
                Mock(spec=Session), "질문", top_k=1, providers=[FakeProvider("jina-v4", 0.1)]
            )

        self.assertIsNone(results[0].source)
        self.assertEqual(results[0].metadata, {})


class SoftBoostTest(unittest.TestCase):
    """ai/rag/CLAUDE.md TODO(진료과 분류 결과를 검색 필터로 쓸지 - 강제 필터 vs
    soft filter)에 대한 결정: 소프트 부스트(곱연산 가중치)를 택했다. 분류기가
    오탐해도 정답 청크가 후보에서 완전히 사라지지 않는지를 검증한다."""

    def test_source_tier_1_outranks_tier_4_when_rrf_scores_are_close(self) -> None:
        document_id = uuid4()
        # RRF 순위상 살짝 밀리지만(2등) 신뢰도가 훨씬 높은 청크(tier 1)가,
        # 순위는 앞서지만(1등) 신뢰도가 낮은 청크(tier 4)를 역전해야 한다.
        low_tier_first = _chunk(document_id, "낮은신뢰도", chunk_metadata={"source_tier": 4})
        high_tier_second = _chunk(document_id, "높은신뢰도", chunk_metadata={"source_tier": 1})
        repository = FakeRepository({"jina-v4": [low_tier_first, high_tier_second]})

        with patch(
            "app.services.rag_search_service.DocumentChunkRepository",
            return_value=repository,
        ):
            results = search(
                Mock(spec=Session), "질문", top_k=2, providers=[FakeProvider("jina-v4", 0.1)]
            )

        self.assertEqual(results[0].text, "높은신뢰도")

    def test_department_match_boosts_matching_chunk_above_higher_ranked_one(self) -> None:
        document_id = uuid4()
        unrelated = _chunk(document_id, "무관", chunk_metadata={"department": ["피부과"]})
        matching = _chunk(document_id, "일치", chunk_metadata={"department": ["정형외과"]})
        repository = FakeRepository({"jina-v4": [unrelated, matching]})

        with patch(
            "app.services.rag_search_service.DocumentChunkRepository",
            return_value=repository,
        ):
            results = search(
                Mock(spec=Session),
                "질문",
                top_k=2,
                providers=[FakeProvider("jina-v4", 0.1)],
                department="정형외과",
            )

        self.assertEqual(results[0].text, "일치")

    def test_no_department_argument_applies_no_department_boost(self) -> None:
        # department를 안 넘기면(예: 분류 실패로 department=None) 진료과 부스트
        # 없이 순수 RRF+신뢰도 부스트만 적용돼야 한다 - 엉뚱하게 아무 진료과나
        # 끌어올리면 안 된다.
        document_id = uuid4()
        first = _chunk(document_id, "A", chunk_metadata={"department": ["피부과"]})
        second = _chunk(document_id, "B", chunk_metadata={"department": ["정형외과"]})
        repository = FakeRepository({"jina-v4": [first, second]})

        with patch(
            "app.services.rag_search_service.DocumentChunkRepository",
            return_value=repository,
        ):
            results = search(
                Mock(spec=Session), "질문", top_k=2, providers=[FakeProvider("jina-v4", 0.1)]
            )

        self.assertEqual([r.text for r in results], ["A", "B"])  # RRF 순위 그대로

    def test_missing_metadata_gets_neutral_multiplier(self) -> None:
        # chunk_metadata가 None(구버전 데이터 등)이어도 예외 없이 그대로 순위가
        # 유지돼야 한다(부스트 없음 = 1.0배).
        document_id = uuid4()
        first = _chunk(document_id, "A", chunk_metadata=None)
        second = _chunk(document_id, "B", chunk_metadata=None)
        repository = FakeRepository({"jina-v4": [first, second]})

        with patch(
            "app.services.rag_search_service.DocumentChunkRepository",
            return_value=repository,
        ):
            results = search(
                Mock(spec=Session),
                "질문",
                top_k=2,
                providers=[FakeProvider("jina-v4", 0.1)],
                department="정형외과",
            )

        self.assertEqual([r.text for r in results], ["A", "B"])


class FakeProvider:
    dimension = 1024

    def __init__(self, name: str, value: float) -> None:
        self.name = name
        self.value = value

    def embed_query(self, text: str) -> list[float]:
        self.query = text
        return [self.value] * 1024

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise AssertionError("검색 시에는 문서 Vector를 다시 생성하면 안 됩니다.")


class FailingProvider:
    dimension = 1024

    def __init__(self, name: str) -> None:
        self.name = name

    def embed_query(self, text: str) -> list[float]:
        raise RemoteEmbeddingError("원격 Embedding 서버에 연결하지 못했습니다.")

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise AssertionError("검색 시에는 문서 Vector를 다시 생성하면 안 됩니다.")


class FakeRepository:
    def __init__(self, rankings: dict[str, list[SimpleNamespace]]) -> None:
        self.rankings = rankings
        self.requested_limits: list[int] = []
        self.query_heads: list[float] = []

    def search_by_provider(self, provider_name, query_vector, top_k):
        self.requested_limits.append(top_k)
        self.query_heads.append(query_vector[0])
        return [
            (chunk, float(rank))
            for rank, chunk in enumerate(self.rankings[provider_name], start=1)
        ]


def _chunk(document_id, text, chunk_metadata=None):
    return SimpleNamespace(
        id=uuid4(),
        document_id=document_id,
        chunk_text=text,
        chunk_metadata=chunk_metadata,
    )


if __name__ == "__main__":
    unittest.main()
