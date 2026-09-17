"""snuh/ClinicalQA 어댑터.

실제 필드(STEP 0 확인 결과):
    question_id, chief_complaint, purpose, question, exam, options(dict-as-string),
    answer(정답 보기 알파벳 한 글자), explanation, source(원문 인용구), category(영문 전공명)

명세가 명시적으로 금지한 것: 객관식 options 자체를 지식으로 저장하는 것. 그래서
content는 question + exam + explanation만 조합한다 - "정답은 C번이다" 같은 시험
문제 형식이 아니라, 실제 임상 추론 설명(explanation)이 지식의 핵심이다.

category는 영문 전공명(예: "Gastroenterology")으로 온다. 진료과 한국어 명칭으로
번역해서 department에 채우는 건 "원본에 없는 진료과를 임의로 확정"하는 것과는
다르다 - 원본이 이미 명시한 전공을 언어만 옮기는 것이라 안전하다고 판단했지만,
매핑표에 없는 전공은 절대 추측하지 않고 빈 리스트로 둔다(generated_metadata=True로
표시해서 "번역해서 만든 값"임을 구분).
"""
from typing import Any

from ...chunking import split_sentences
from ..schema import NormalizedRecord
from .base import DatasetAdapter

SOURCE = "snuh/ClinicalQA"
SOURCE_TYPE = "clinical_qa"

# 원본이 준 영문 전공명 -> 한국어 진료과 명칭. 확실히 대응되는 것만 채운다 - 모호한
# 건 절대 추측해서 채우지 않는다(빈 리스트로 남김).
_CATEGORY_TO_DEPARTMENT: dict[str, str] = {
    "gastroenterology": "소화기내과",
    "cardiology": "순환기내과",
    "pulmonology": "호흡기내과",
    "nephrology": "신장내과",
    "endocrinology": "내분비내과",
    "neurology": "신경과",
    "dermatology": "피부과",
    "orthopedics": "정형외과",
    "psychiatry": "정신건강의학과",
    "ophthalmology": "안과",
    "otolaryngology": "이비인후과",
    "urology": "비뇨의학과",
    "obstetrics and gynecology": "산부인과",
    "pediatrics": "소아청소년과",
}


# 실제 데이터에서 관찰된 객관식 시험 문제 형식의 "마무리 질문" 신호 - "다음 중"으로
# 시작하지 않는 경우도 있어서("...가장 가능성이 높은 진단은?") 문구 몇 개를 더 본다.
# 이 신호들과 함께 "?"로 끝나는 마지막 문장만 제외한다(일반 물음표 문장까지 넓게
# 지우면 실제 의료 서술을 훼손할 수 있어 신호 있는 것만 좁게 잡는다).
_MCQ_PROMPT_SIGNALS = ("다음 중", "가능성이 높은", "가장 적절한", "가장 흔한")


def _strip_trailing_mcq_prompt(question: str) -> str:
    """일부 문항은 임상 증례 설명 뒤에 "다음 중 ... 가장 가능성이 높은 질환은?" 같은
    객관식 시험 문제 형식의 마지막 문장이 붙어서 온다. 이런 문장은 의료 지식이 아니라
    시험 문항 형식 자체라 RAG content에서는 제외한다 - question 필드 원본은 그대로
    두고(NormalizedRecord.question), content 조합에만 반영한다(원본 훼손 아님).
    전부 이 형식이라 남는 문장이 없으면 원본을 그대로 돌려준다(내용을 통째로
    비우지 않기 위함)."""
    sentences = split_sentences(question)
    while sentences and sentences[-1].rstrip().endswith("?") and any(
        signal in sentences[-1] for signal in _MCQ_PROMPT_SIGNALS
    ):
        sentences.pop()
    return " ".join(sentences).strip() or question


class SnuhClinicalQaAdapter(DatasetAdapter):
    source = SOURCE
    source_type = SOURCE_TYPE
    hf_path = "snuh/ClinicalQA"

    def to_normalized(self, raw_row: dict[str, Any], index: int) -> NormalizedRecord | None:
        question = str(raw_row.get("question") or "").strip()
        explanation = str(raw_row.get("explanation") or "").strip()
        if not question or not explanation:
            return None

        exam = str(raw_row.get("exam") or "").strip()
        chief_complaint = str(raw_row.get("chief_complaint") or "").strip()

        parts = [_strip_trailing_mcq_prompt(question)]
        if exam:
            parts.append(exam)
        parts.append(explanation)
        content = "\n\n".join(parts)

        original_id = str(raw_row.get("question_id") or index)
        category = str(raw_row.get("category") or "").strip() or None
        department, generated = self._map_department(category)

        # 실제 HF dataset card 원문 재확인 결과 - "Clinical review: Verified for
        # medical accuracy by three clinicians"라고 명시적으로 적혀 있다(단순
        # "검수"가 아니라 "의료진 3명이 의료 정확성을 검증"). AI 생성이지만 구체적인
        # 전문가 검수 절차가 명시된 경우라 "낮음"보다는 명확히 높게 본다 - source_tier
        # 2단계(전문가 검수, 원문 그대로 저작은 아니라 1단계는 아님).
        metadata: dict[str, Any] = {
            "language": "ko",
            "content_type": "clinical_reasoning",
            "reliability": "expert_reviewed_ai_generated",
            "reliability_tier": "높음",
            "reliability_reason": (
                "SNUH-HARI(서울대병원 산하 연구소) 큐레이션, GPT-4o 등으로 생성 후 "
                "의료진 3명이 의료 정확성 검증(카드 원문: 'Verified for medical "
                "accuracy by three clinicians')"
            ),
            "source_tier": 2,
            "verification_status": "clinician_reviewed",
        }
        if generated:
            metadata["generated_metadata"] = True
        source_citation = str(raw_row.get("source") or "").strip()
        if source_citation:
            metadata["reference"] = source_citation

        return NormalizedRecord(
            source=SOURCE,
            source_type=SOURCE_TYPE,
            content=content,
            original_id=original_id,
            original_dataset=self.hf_path,
            title=chief_complaint or None,
            question=question,
            answer=explanation,
            category=category,
            department=department,
            metadata=metadata,
        )

    @staticmethod
    def _map_department(category: str | None) -> tuple[list[str], bool]:
        if not category:
            return [], False
        mapped = _CATEGORY_TO_DEPARTMENT.get(category.strip().lower())
        return ([mapped], True) if mapped else ([], False)
