import unittest
from unittest.mock import patch

from ai.llm import (
    LlmApplicationService,
    LlmModelDefinition,
    LlmProviderUnavailableError,
    ProviderAvailability,
    ProviderGenerateResult,
    ProviderRegistry,
)
from app.services import llm_runtime, llm_service


class FakeRemoteProvider:
    key = "remote-http"
    is_mock = False

    def __init__(self, *, failing_model_id: str | None = None) -> None:
        self.failing_model_id = failing_model_id
        self.requests = []

    async def check_availability(self, model: LlmModelDefinition) -> ProviderAvailability:
        del model
        return ProviderAvailability(True)

    async def generate(self, request, model):
        self.requests.append(request)
        if model.id == self.failing_model_id:
            raise LlmProviderUnavailableError("테스트 모델 실행 실패")
        return ProviderGenerateResult(answer=f"{model.id} 응답")


class LlmApiTest(unittest.TestCase):
    def setUp(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.api.auth.dependencies import get_current_user, require_admin
        from app.api.llm.router import router as llm_router

        self.provider = FakeRemoteProvider()
        self.application = LlmApplicationService(
            llm_runtime.create_model_registry(),
            ProviderRegistry((self.provider,)),
        )
        app = FastAPI()
        app.include_router(llm_router, prefix="/api/llm")
        app.dependency_overrides[get_current_user] = lambda: object()
        app.dependency_overrides[require_admin] = lambda: object()
        self.client = TestClient(app)

    def test_models_keep_existing_snake_case_contract(self) -> None:
        with patch.object(llm_service, "llm_application", self.application):
            response = self.client.get("/api/llm/models")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["model_id"] for item in response.json()],
            ["gemma", "medgemma", "medgemma-dataset", "qwen", "llama"],
        )

    def test_generate_keeps_message_roles_and_response_contract(self) -> None:
        with patch.object(llm_service, "llm_application", self.application):
            response = self.client.post(
                "/api/llm/generate",
                json={
                    "model_id": "medgemma",
                    "messages": [
                        {"role": "user", "content": "첫 질문"},
                        {"role": "assistant", "content": "첫 답변"},
                        {"role": "user", "content": "후속 질문"},
                    ],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"model_id": "medgemma", "content": "medgemma 응답"},
        )
        self.assertEqual(
            [message.role for message in self.provider.requests[0].messages],
            ["user", "assistant", "user"],
        )

    def test_unknown_model_keeps_404_contract(self) -> None:
        with patch.object(llm_service, "llm_application", self.application):
            response = self.client.post(
                "/api/llm/generate",
                json={
                    "model_id": "unknown",
                    "messages": [{"role": "user", "content": "질문"}],
                },
            )

        self.assertEqual(response.status_code, 404)

    def test_invalid_message_role_is_rejected_before_core_call(self) -> None:
        with patch.object(llm_service, "llm_application", self.application):
            response = self.client.post(
                "/api/llm/generate",
                json={
                    "model_id": "medgemma",
                    "messages": [{"role": "tool", "content": "잘못된 Role"}],
                },
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.provider.requests, [])

    def test_compare_isolates_one_model_failure(self) -> None:
        provider = FakeRemoteProvider(failing_model_id="qwen")
        application = LlmApplicationService(
            llm_runtime.create_model_registry(),
            ProviderRegistry((provider,)),
        )
        with patch.object(llm_service, "llm_application", application):
            response = self.client.post(
                "/api/llm/compare",
                json={
                    "model_ids": ["gemma", "qwen"],
                    "messages": [{"role": "user", "content": "질문"}],
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload[0]["content"], "gemma 응답")
        self.assertIsNone(payload[0]["error"])
        self.assertIsNone(payload[1]["content"])
        self.assertIn("실행 실패", payload[1]["error"])


if __name__ == "__main__":
    unittest.main()
