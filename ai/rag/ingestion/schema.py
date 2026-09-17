"""HuggingFace 데이터셋마다 스키마가 다 다르므로, 각 어댑터가 만들어내는 공통 중간
표현. 여기서부터는 어떤 데이터셋에서 왔는지 몰라도 cleaning/dedup/chunking을 똑같이
적용할 수 있다.

`original_id`/`original_dataset`을 필수 필드로 둔 이유: 이 둘이 곧 idempotency 키의
일부다(dedup.py, backend의 rag_bulk_ingestion_service.py 참고) — optional로 두면
어댑터가 깜빡하고 안 채워도 타입 체커가 못 잡는다.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class NormalizedRecord:
    source: str
    """데이터셋을 사람이 알아볼 수 있는 이름 (예: "Asan-AMC-Healthinfo") — provenance용,
    HuggingFace repo 경로(original_dataset)와는 별개로 사람이 읽는 라벨."""
    source_type: str
    """예: "hospital_health_information", "clinical_qa" — chunk metadata의 content_type과
    유사하지만 문서 단위 분류."""
    content: str
    """실제로 chunking 대상이 되는 텍스트. 어댑터가 원본 필드(question/answer/explanation
    등)를 조합해서 만든다 — 원본에 없는 내용을 지어내지 않고, 있는 필드만 이어붙인다."""
    original_id: str
    """원본 데이터셋 안에서 이 행을 가리키는 식별자(행 인덱스도 허용). 비어있으면 안 된다."""
    original_dataset: str
    """HuggingFace repo 경로 그대로 (예: "ChuGyouk/Asan-AMC-Healthinfo")."""
    title: str | None = None
    question: str | None = None
    answer: str | None = None
    category: str | None = None
    department: list[str] = field(default_factory=list)
    disease: list[str] = field(default_factory=list)
    symptoms: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    """department/disease/symptoms 등 위에 이름 붙은 필드 이외에, 데이터셋별로 남겨두고
    싶은 부가 정보(예: snuh/ClinicalQA의 원문 인용구, reliability 플래그 등)."""

    def __post_init__(self) -> None:
        if not self.original_id:
            raise ValueError("NormalizedRecord.original_id는 비어있으면 안 됩니다.")
        if not self.original_dataset:
            raise ValueError("NormalizedRecord.original_dataset은 비어있으면 안 됩니다.")
