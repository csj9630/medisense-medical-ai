import sys
import types
import unittest
from unittest.mock import MagicMock

from ai.rag.embeddings.sentence_transformer import SentenceTransformerEmbeddingProvider


class _FakeModel:
    """실제 sentence-transformers 모델 다운로드 없이 `.encode()` 계약만 흉내낸다."""

    def __init__(self, dimension: int = 8) -> None:
        self.dimension = dimension
        self.encode_calls: list[dict] = []

    def get_sentence_embedding_dimension(self) -> int:
        return self.dimension

    def encode(self, texts, **kwargs):
        self.encode_calls.append({"texts": texts, **kwargs})
        return [[0.1] * self.dimension for _ in texts]


class SentenceTransformerEmbeddingProviderTest(unittest.TestCase):
    def setUp(self) -> None:
        # 실제 라이브러리를 설치/다운로드하지 않고 provider가 그 자리에서 import하는
        # `sentence_transformers.SentenceTransformer`를 가짜 모듈로 바꿔치기한다.
        self.fake_model = _FakeModel(dimension=8)
        self.constructor = MagicMock(return_value=self.fake_model)
        fake_module = types.ModuleType("sentence_transformers")
        fake_module.SentenceTransformer = self.constructor
        self._patched_module = fake_module
        self._original_module = sys.modules.get("sentence_transformers")
        sys.modules["sentence_transformers"] = fake_module

    def tearDown(self) -> None:
        if self._original_module is not None:
            sys.modules["sentence_transformers"] = self._original_module
        else:
            sys.modules.pop("sentence_transformers", None)

    def test_name_defaults_to_model_name(self) -> None:
        provider = SentenceTransformerEmbeddingProvider("BAAI/bge-m3")
        self.assertEqual(provider.name, "BAAI/bge-m3")

    def test_custom_name_overrides_model_name(self) -> None:
        provider = SentenceTransformerEmbeddingProvider("BAAI/bge-m3", name="bge-m3")
        self.assertEqual(provider.name, "bge-m3")

    def test_model_is_not_loaded_until_first_embed_call(self) -> None:
        SentenceTransformerEmbeddingProvider("BAAI/bge-m3")
        self.constructor.assert_not_called()

    def test_dimension_autodetected_from_model_when_not_given(self) -> None:
        provider = SentenceTransformerEmbeddingProvider("BAAI/bge-m3")
        self.assertEqual(provider.dimension, 0)  # 로드 전에는 0
        provider.embed_query("두통이 있어요")
        self.assertEqual(provider.dimension, 8)

    def test_second_call_reuses_loaded_model(self) -> None:
        provider = SentenceTransformerEmbeddingProvider("BAAI/bge-m3")
        provider.embed_query("첫 번째 질문")
        provider.embed_query("두 번째 질문")
        self.constructor.assert_called_once()

    def test_embed_texts_uses_document_prompt_name(self) -> None:
        provider = SentenceTransformerEmbeddingProvider(
            "BAAI/bge-m3", document_prompt_name="passage"
        )
        provider.embed_texts(["문서 내용"])
        self.assertEqual(self.fake_model.encode_calls[-1]["prompt_name"], "passage")

    def test_embed_query_uses_query_prompt_name(self) -> None:
        provider = SentenceTransformerEmbeddingProvider(
            "BAAI/bge-m3", query_prompt_name="query"
        )
        provider.embed_query("사용자 질문")
        self.assertEqual(self.fake_model.encode_calls[-1]["prompt_name"], "query")

    def test_embed_texts_empty_list_returns_empty_without_loading_model(self) -> None:
        provider = SentenceTransformerEmbeddingProvider("BAAI/bge-m3")
        self.assertEqual(provider.embed_texts([]), [])
        self.constructor.assert_not_called()

    def test_truncate_dim_passed_to_encode_and_used_as_dimension(self) -> None:
        provider = SentenceTransformerEmbeddingProvider("jinaai/jina-embeddings-v4", truncate_dim=4)
        provider.embed_query("텍스트")
        self.assertEqual(self.fake_model.encode_calls[-1]["truncate_dim"], 4)
        self.assertEqual(provider.dimension, 4)

    def test_revision_and_trust_remote_code_passed_to_constructor(self) -> None:
        provider = SentenceTransformerEmbeddingProvider(
            "some/model", revision="abc123", trust_remote_code=True
        )
        provider.embed_query("텍스트")
        self.constructor.assert_called_once_with(
            "some/model", revision="abc123", trust_remote_code=True
        )

    def test_trust_remote_code_defaults_to_false(self) -> None:
        provider = SentenceTransformerEmbeddingProvider("some/model")
        provider.embed_query("텍스트")
        _, kwargs = self.constructor.call_args
        self.assertFalse(kwargs["trust_remote_code"])


if __name__ == "__main__":
    unittest.main()
