"""소스 이름(CLI --source 값) -> 어댑터 클래스. 새 데이터셋을 추가할 땐 여기에
한 줄만 더하면 CLI/파이프라인/backend 브릿지 전부 자동으로 그 데이터셋을 다룰 수
있게 된다.
"""
from .ai_healthcare_qa import AiHealthcareQaAdapter
from .asan import AsanHealthInfoAdapter
from .base import DatasetAdapter
from .genmed_gpt import GenMedGptAdapter
from .health_search_qa import HealthSearchQaAdapter
from .kdca_openapi import KdcaOpenApiAdapter
from .komed_instruct import KoMedInstructAdapter
from .snuh_clinical_qa import SnuhClinicalQaAdapter

ADAPTERS: dict[str, type[DatasetAdapter]] = {
    "asan": AsanHealthInfoAdapter,
    "snuh-clinical-qa": SnuhClinicalQaAdapter,
    "health-search-qa": HealthSearchQaAdapter,
    "ai-healthcare-qa": AiHealthcareQaAdapter,
    "komed-instruct": KoMedInstructAdapter,
    "genmed-gpt": GenMedGptAdapter,
    "kdca-openapi": KdcaOpenApiAdapter,
}


def get_adapter(name: str) -> DatasetAdapter:
    adapter_cls = ADAPTERS.get(name)
    if adapter_cls is None:
        available = ", ".join(sorted(ADAPTERS))
        raise ValueError(f"알 수 없는 데이터셋 이름입니다: {name!r} (사용 가능: {available})")
    return adapter_cls()
