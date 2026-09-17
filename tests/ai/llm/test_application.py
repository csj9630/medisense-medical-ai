import unittest

from ai.llm import (
    LlmApplicationService,
    ModelRegistry,
    ProviderRegistry,
    UnknownLlmModelError,
)
from tests.ai.llm.helpers import FakeProvider, model_definition, prompt_request


class RegistryAndApplicationTest(unittest.IsolatedAsyncioTestCase):
    async def test_provider_key_switches_without_application_change(self) -> None:
        mock_provider = FakeProvider("mock", is_mock=True)
        ollama_provider = FakeProvider("ollama", is_mock=False)
        providers = ProviderRegistry((mock_provider, ollama_provider))

        mock_app = LlmApplicationService(
            ModelRegistry((model_definition(model_id="medgemma", provider_key="mock"),)),
            providers,
        )
        real_app = LlmApplicationService(
            ModelRegistry((model_definition(model_id="medgemma", provider_key="ollama"),)),
            providers,
        )

        mock_result = await mock_app.run("medgemma", prompt_request())
        real_result = await real_app.run("medgemma", prompt_request())

        self.assertTrue(mock_result.is_mock)
        self.assertFalse(real_result.is_mock)
        self.assertEqual(real_result.provider, "ollama")

    async def test_catalog_reports_missing_provider_without_crashing(self) -> None:
        app = LlmApplicationService(
            ModelRegistry((model_definition(provider_key="missing"),)),
            ProviderRegistry(()),
        )

        entries = await app.list_models()

        self.assertEqual(len(entries), 1)
        self.assertFalse(entries[0].availability.available)
        self.assertIn("등록되지", entries[0].availability.message or "")

    def test_unknown_model_is_rejected(self) -> None:
        registry = ModelRegistry(())
        with self.assertRaises(UnknownLlmModelError):
            registry.resolve("unknown")


if __name__ == "__main__":
    unittest.main()
