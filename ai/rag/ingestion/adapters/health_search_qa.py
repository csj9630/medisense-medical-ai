"""ChuGyouk/HealthSearchQA-ko 어댑터.

실제 필드(STEP 0 확인 결과): id, question(영문 원본), answer_ko, question_ko.
한국어 RAG이므로 question_ko/answer_ko만 쓰고 영문 원본(question)은 참고용으로만
metadata에 남긴다.
"""
from typing import Any

from ..schema import NormalizedRecord
from .base import DatasetAdapter

SOURCE = "HealthSearchQA-ko"
SOURCE_TYPE = "consumer_health_qa"


class HealthSearchQaAdapter(DatasetAdapter):
    source = SOURCE
    source_type = SOURCE_TYPE
    hf_path = "ChuGyouk/HealthSearchQA-ko"

    def to_normalized(self, raw_row: dict[str, Any], index: int) -> NormalizedRecord | None:
        question_ko = str(raw_row.get("question_ko") or "").strip()
        answer_ko = str(raw_row.get("answer_ko") or "").strip()
        if not question_ko or not answer_ko:
            return None

        content = f"{question_ko}\n\n{answer_ko}"
        original_id = str(raw_row.get("id") or index)
        question_en = str(raw_row.get("question") or "").strip()

        return NormalizedRecord(
            source=SOURCE,
            source_type=SOURCE_TYPE,
            content=content,
            original_id=original_id,
            original_dataset=self.hf_path,
            title=question_ko,
            question=question_ko,
            answer=answer_ko,
            # 실제 HF dataset card 확인 결과 - 질문은 Med-PaLM의 HealthSearchQA를 번역,
            # 답변은 gpt-4o-2024-05-13이 그대로 생성(전문가 검수 언급 없음). 팀
            # 지시서 5-1절 "낮음"(LLM 자동 생성, 검수 여부 불명) 기준.
            metadata={
                "language": "ko",
                "content_type": "consumer_qa",
                "reliability": "ai_generated_unverified",
                "reliability_tier": "낮음",
                "reliability_reason": "질문은 Med-PaLM HealthSearchQA 번역, 답변은 gpt-4o가 생성(전문가 검수 언급 없음)",
                "source_tier": 3,
                "verification_status": "llm_generated_unverified",
                **({"question_en": question_en} if question_en else {}),
            },
        )
