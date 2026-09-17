"""공통 Model/Provider Registry와 MedGemma Adapter 정의입니다."""

from collections.abc import Iterable
from dataclasses import dataclass

from ai.llm.contracts import (
    LlmModelDefinition,
    LlmProvider,
    LlmProviderUnavailableError,
    UnknownLlmModelError,
)


class ModelRegistry:
    def __init__(self, definitions: Iterable[LlmModelDefinition]) -> None:
        self._definitions = {definition.id: definition for definition in definitions}

    def list(self) -> tuple[LlmModelDefinition, ...]:
        return tuple(self._definitions.values())

    def resolve(self, model_id: str) -> LlmModelDefinition:
        definition = self._definitions.get(model_id)
        if definition is None:
            raise UnknownLlmModelError(f"지원하지 않는 모델입니다: {model_id}")
        return definition


class ProviderRegistry:
    def __init__(self, providers: Iterable[LlmProvider]) -> None:
        self._providers = {provider.key: provider for provider in providers}

    def resolve(self, provider_key: str) -> LlmProvider:
        provider = self._providers.get(provider_key)
        if provider is None:
            raise LlmProviderUnavailableError(
                f"LLM Provider가 등록되지 않았습니다: {provider_key}"
            )
        return provider


MEDGEMMA_MODEL_DEFINITIONS: tuple[LlmModelDefinition, ...] = (
    LlmModelDefinition(
        id="medgemma-screening",
        provider_key="medgemma",
        provider_model="gon-0130/medgemma-4b-lora-consultation",
        label="MedGemma (스크리닝)",
        family="MedGemma LoRA",
        training_stage="초기 학습 버전",
        description="무료 Colab에서 학습한 초기 버전 — KorMedMCQA + GenMedGPT-5k-ko 2종.",
        group="other",
    ),
    LlmModelDefinition(
        id="medgemma-main",
        provider_key="medgemma",
        provider_model="gon-0130/medgemma-4b-lora-consultation-main-v2",
        label="MedGemma (메인)",
        family="MedGemma LoRA",
        training_stage="메인 학습 버전",
        description="유료 Colab에서 학습한 메인 버전 — 지식/추론보강/대화형 11개 데이터셋.",
        group="other",
    ),
)

QWEN_MODEL_DEFINITIONS: tuple[LlmModelDefinition, ...] = (
    LlmModelDefinition(
        id="qwen-medical",
        provider_key="qwen",
        provider_model="csj9630/qwen3-4b-medical-qlora",
        label="Qwen3 (의료 LoRA)",
        family="Qwen3 LoRA",
        training_stage="QLoRA 4bit SFT",
        description="Qwen/Qwen3-4B 기반, KorMedMCQA + GenMedGPT-5k-ko로 미세조정한 의료 어댑터.",
        group="other",
    ),
)

# meta-llama/Llama-3.2-3B-Instruct는 HuggingFace Gated Repo다 — HF_TOKEN 계정이 Meta
# 라이선스에 동의하고 접근 승인을 받아야 실제로 로드된다. 승인 전에는 항상 unavailable로
# 뜨지만(ai/llm/engine.py의 GatedRepoError 처리 참고), 정의 자체는 미리 등록해둔다 —
# 접근 승인이 나면 코드 변경 없이 바로 쓸 수 있게 하기 위함("준비만 해두기").
LLAMA_MODEL_DEFINITIONS: tuple[LlmModelDefinition, ...] = (
    LlmModelDefinition(
        id="llama-medical",
        provider_key="llama",
        provider_model="csj9630/llama32-3b-medical-qlora",
        label="Llama 3.2 (의료 LoRA)",
        family="Llama 3.2 LoRA",
        training_stage="QLoRA 4bit SFT",
        description=(
            "meta-llama/Llama-3.2-3B-Instruct 기반, KorMedMCQA + GenMedGPT-5k-ko로 "
            "미세조정한 의료 어댑터. Base 모델이 Gated Repo라 이 프로젝트의 HF 계정이 "
            "Meta 라이선스 접근 승인을 받기 전까지는 항상 unavailable로 표시된다."
        ),
        group="other",
    ),
)


@dataclass(frozen=True)
class ModelEntry:
    """기존 `/api/llm/models`와 Engine 호출을 위한 호환 Projection입니다."""

    model_id: str
    adapter_repo: str
    label: str
    description: str


MODEL_REGISTRY: list[ModelEntry] = [
    ModelEntry(
        model_id=definition.id,
        adapter_repo=definition.provider_model,
        label=definition.label,
        description=definition.description,
    )
    for definition in MEDGEMMA_MODEL_DEFINITIONS
]

DEFAULT_MODEL_ID = MODEL_REGISTRY[0].model_id


def get_model_entry(model_id: str) -> ModelEntry:
    for entry in MODEL_REGISTRY:
        if entry.model_id == model_id:
            return entry
    raise KeyError(f"등록되지 않은 model_id입니다: {model_id}")


def list_models() -> list[ModelEntry]:
    return list(MODEL_REGISTRY)
