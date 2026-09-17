"""ChuGyouk/Asan-AMC-Healthinfo 어댑터.

실제 필드(STEP 0 확인 결과) - Alpaca 스타일 instruction/input/output:
    instruction: "경피적 간담도조영술의 정의에 대해서 설명해주세요." (질문형 제목)
    input: "" (거의 항상 비어있음)
    output: 실제 의료 정보 설명 본문

명세가 우려하는 "질문+답변을 그대로 embedding" 문제를 피하기 위해, instruction을
그대로 검색 대상 텍스트로 쓰지 않고 "제목" 역할로만 쓰고, 실제 검색/근거 텍스트는
output(진짜 의료 지식)이 중심이 되도록 합친다. input이 비어있지 않은 드문 경우를
대비해 있으면 이어붙인다.
"""
from typing import Any

from ..schema import NormalizedRecord
from .base import DatasetAdapter

SOURCE = "Asan-AMC-Healthinfo"
SOURCE_TYPE = "hospital_health_information"


class AsanHealthInfoAdapter(DatasetAdapter):
    source = SOURCE
    source_type = SOURCE_TYPE
    hf_path = "ChuGyouk/Asan-AMC-Healthinfo"

    def to_normalized(self, raw_row: dict[str, Any], index: int) -> NormalizedRecord | None:
        instruction = str(raw_row.get("instruction") or "").strip()
        output = str(raw_row.get("output") or "").strip()
        extra_input = str(raw_row.get("input") or "").strip()
        if not instruction or not output:
            return None

        parts = [instruction, output]
        if extra_input:
            parts.append(extra_input)
        content = "\n\n".join(parts)

        return NormalizedRecord(
            source=SOURCE,
            source_type=SOURCE_TYPE,
            content=content,
            original_id=str(index),
            original_dataset=self.hf_path,
            title=instruction,
            answer=output,
            # 실제 HF dataset card 확인 결과 - 서울아산병원 공식 홈페이지 건강정보
            # 원문을 그대로 편집한 데이터(생성/번역 아님). 팀 지시서 5-1절 "매우 높음"
            # (대학병원 공식 자료) 기준에 해당한다.
            metadata={
                "language": "ko",
                "content_type": "disease_information",
                "reliability": "verified_official",
                "reliability_tier": "매우 높음",
                "reliability_reason": "서울아산병원 공식 홈페이지 건강정보 원문 편집(생성/번역 아님)",
                "source_tier": 1,
                "verification_status": "official_source",
            },
        )
