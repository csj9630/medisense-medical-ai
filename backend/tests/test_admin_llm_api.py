import json
import unittest
from unittest.mock import AsyncMock, patch

from ai.llm import (
    LlmApplicationService,
    LlmModelDefinition,
    LlmProviderUnavailableError,
    ProviderAvailability,
    ProviderGenerateResult,
    ProviderRegistry,
)
from app.services import admin_llm, llm_runtime


class FakeProvider:
    def __init__(
        self,
        key: str,
        *,
        is_mock: bool,
        should_fail: bool = False,
        failing_model_id: str | None = None,
    ) -> None:
        self.key = key
        self.is_mock = is_mock
        self.should_fail = should_fail
        self.failing_model_id = failing_model_id
        self.generate = AsyncMock(side_effect=self._generate)

    async def _generate(self, request, model):
        del request
        if self.should_fail or model.id == self.failing_model_id:
            raise LlmProviderUnavailableError("테스트 Provider 실패")
        return ProviderGenerateResult(
            answer=f"{model.id} answer",
            input_tokens=10,
            output_tokens=20,
            total_tokens=30,
            finish_reason="stop",
        )

    async def check_availability(self, model: LlmModelDefinition) -> ProviderAvailability:
        del model
        return ProviderAvailability(not self.should_fail)


class AdminLlmApiTest(unittest.TestCase):
    def setUp(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.api.admin.router import router as admin_router
        from app.api.auth.dependencies import require_admin

        self.providers = (FakeProvider("remote-http", is_mock=False),)
        self.application = LlmApplicationService(
            llm_runtime.create_model_registry(),
            ProviderRegistry(self.providers),
        )
        app = FastAPI()
        app.include_router(admin_router, prefix="/api/admin")
        app.dependency_overrides[require_admin] = lambda: object()
        self.client = TestClient(app)

    def test_model_catalog_and_run_keep_camel_case_contract(self) -> None:
        with patch.object(admin_llm, "llm_application", self.application):
            catalog_response = self.client.get("/api/admin/llm/models")
            run_response = self.client.post(
                "/api/admin/llm/run",
                json={
                    "prompt": "질문",
                    "modelId": "gemma",
                    "documentNames": ["first.pdf", "second.png"],
                },
            )

        self.assertEqual(catalog_response.status_code, 200)
        catalog = catalog_response.json()
        self.assertEqual(len(catalog), 5)
        self.assertEqual(
            [model["id"] for model in catalog],
            ["gemma", "medgemma", "medgemma-dataset", "qwen", "llama"],
        )
        self.assertTrue(all(not model["isMock"] for model in catalog))
        self.assertNotIn("gemini", [model["id"] for model in catalog])
        self.assertNotIn("apiKey", json.dumps(catalog))

        self.assertEqual(run_response.status_code, 200)
        payload = run_response.json()
        self.assertEqual(payload["provider"], "remote-http")
        self.assertEqual(payload["providerModel"], "gemma")
        self.assertFalse(payload["isMock"])
        self.assertEqual(payload["totalTokens"], 30)

        request = self.providers[0].generate.await_args.args[0]  # type: ignore[union-attr]
        self.assertEqual(request.messages[0].role, "user")
        self.assertEqual(request.messages[0].content, "질문")
        self.assertEqual(request.document_name, "first.pdf, second.png")

    def test_unknown_model_returns_422(self) -> None:
        with patch.object(admin_llm, "llm_application", self.application):
            response = self.client.post(
                "/api/admin/llm/run",
                json={"prompt": "질문", "modelId": "main-fine-tuned"},
            )

        self.assertEqual(response.status_code, 422)

    def test_compare_isolates_one_provider_failure(self) -> None:
        providers = ProviderRegistry(
            (FakeProvider("remote-http", is_mock=False, failing_model_id="qwen"),)
        )
        application = LlmApplicationService(
            llm_runtime.create_model_registry(),
            providers,
        )

        with patch.object(admin_llm, "llm_application", application):
            response = self.client.post(
                "/api/admin/llm/compare",
                json={
                    "prompt": "질문",
                    "modelIds": ["gemma", "qwen"],
                    "chunkSize": 512,
                    "overlap": 50,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload[0]["status"], "success")
        self.assertEqual(payload[1]["status"], "error")
        self.assertNotIn("Traceback", payload[1]["error"])


if __name__ == "__main__":
    unittest.main()
