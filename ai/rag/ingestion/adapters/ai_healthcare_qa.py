"""ChuGyouk/AI_healthcare_QA - STEP 0에서 실제로 접근을 시도한 결과, HuggingFace에서
gated(승인 필요) 데이터셋으로 확인됐다. 이 세션에서 갖고 있는 HF 토큰으로도
`DatasetNotFoundError: ... is a gated dataset ...`가 발생했다 - 계정이 아직 접근
승인을 못 받은 상태.

명세의 fallback 지침(하나의 데이터셋 때문에 전체 작업을 막지 않는다)에 따라, 이
어댑터는 자리만 채워두고 실제 동작은 명확한 에러를 낸다. 접근 승인을 받으면
`GatedDatasetAdapter`가 아니라 다른 어댑터들과 같은 `DatasetAdapter`를 상속하도록
바꾸고 STEP 0(실제 필드 확인)부터 다시 진행해야 한다 - 지금은 필드조차 확인 못한
상태라 스키마를 추측해서 구현하지 않는다.

접근 승인 절차: https://huggingface.co/datasets/ChuGyouk/AI_healthcare_QA 페이지에서
접근 요청 -> 데이터셋 소유자 승인 대기.
"""
from .base import GatedDatasetAdapter

SOURCE = "AI_healthcare_QA"
SOURCE_TYPE = "ai_generated_qa"


class AiHealthcareQaAdapter(GatedDatasetAdapter):
    source = SOURCE
    source_type = SOURCE_TYPE
    hf_path = "ChuGyouk/AI_healthcare_QA"
    reason = (
        "HuggingFace에서 gated 데이터셋 - 접근 승인이 필요합니다. "
        "https://huggingface.co/datasets/ChuGyouk/AI_healthcare_QA 에서 접근 요청 후 재시도하세요."
    )
