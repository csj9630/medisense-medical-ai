import unittest

from ai.llm import (
    LLAMA_MODEL_DEFINITIONS,
    MEDGEMMA_MODEL_DEFINITIONS,
    MODEL_REGISTRY,
    QWEN_MODEL_DEFINITIONS,
    ModelRegistry,
)


class MedGemmaRegistryTest(unittest.TestCase):
    def test_compatibility_projection_uses_canonical_definitions(self) -> None:
        definitions = ModelRegistry(MEDGEMMA_MODEL_DEFINITIONS).list()

        self.assertEqual(
            [definition.id for definition in definitions],
            ["medgemma-screening", "medgemma-main"],
        )
        self.assertEqual(
            [entry.model_id for entry in MODEL_REGISTRY],
            [definition.id for definition in definitions],
        )
        self.assertEqual(
            [entry.adapter_repo for entry in MODEL_REGISTRY],
            [definition.provider_model for definition in definitions],
        )
        self.assertTrue(all(definition.provider_key == "medgemma" for definition in definitions))


class QwenLlamaRegistryTest(unittest.TestCase):
    def test_qwen_definition_points_at_real_adapter_repo(self) -> None:
        (definition,) = QWEN_MODEL_DEFINITIONS
        self.assertEqual(definition.id, "qwen-medical")
        self.assertEqual(definition.provider_key, "qwen")
        self.assertEqual(definition.provider_model, "csj9630/qwen3-4b-medical-qlora")

    def test_llama_definition_points_at_real_adapter_repo(self) -> None:
        (definition,) = LLAMA_MODEL_DEFINITIONS
        self.assertEqual(definition.id, "llama-medical")
        self.assertEqual(definition.provider_key, "llama")
        self.assertEqual(definition.provider_model, "csj9630/llama32-3b-medical-qlora")

    def test_no_id_collisions_across_all_definition_groups(self) -> None:
        all_ids = [
            d.id
            for group in (MEDGEMMA_MODEL_DEFINITIONS, QWEN_MODEL_DEFINITIONS, LLAMA_MODEL_DEFINITIONS)
            for d in group
        ]
        self.assertEqual(len(all_ids), len(set(all_ids)))


if __name__ == "__main__":
    unittest.main()
