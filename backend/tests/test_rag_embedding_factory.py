import unittest

from ai.rag import (
    HashingEmbeddingProvider,
    RemoteEmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
)
from app.core.config import Settings
from app.core.rag_embedding import (
    build_rag_embedding_provider,
    build_rag_embedding_providers,
)


def _settings(**overrides) -> Settings:
    # 실제 .env를 안 읽고 필드만 오버라이드한 최소 Settings를 만든다.
    return Settings(_env_file=None, **overrides)


class BuildRagEmbeddingProviderTest(unittest.TestCase):
    def test_remote_dual_is_the_default(self) -> None:
        providers = build_rag_embedding_providers(_settings())

        self.assertEqual(len(providers), 2)
        self.assertTrue(all(isinstance(item, RemoteEmbeddingProvider) for item in providers))
        self.assertEqual([item.name for item in providers], ["jina-v4", "medical-bgem3"])
        self.assertTrue(all(item.dimension == 1024 for item in providers))

    def test_hashing_remains_available_for_local_development(self) -> None:
        provider = build_rag_embedding_provider(
            _settings(rag_embedding_provider="hashing")
        )
        self.assertIsInstance(provider, HashingEmbeddingProvider)

    def test_sentence_transformer_selected_by_name(self) -> None:
        provider = build_rag_embedding_provider(
            _settings(
                rag_embedding_provider="sentence_transformer",
                rag_embedding_model_name="BAAI/bge-m3",
            )
        )
        self.assertIsInstance(provider, SentenceTransformerEmbeddingProvider)
        self.assertEqual(provider.name, "BAAI/bge-m3")

    def test_sentence_transformer_without_model_name_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_rag_embedding_provider(_settings(rag_embedding_provider="sentence_transformer"))

    def test_unknown_provider_name_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_rag_embedding_provider(_settings(rag_embedding_provider="does-not-exist"))


if __name__ == "__main__":
    unittest.main()
