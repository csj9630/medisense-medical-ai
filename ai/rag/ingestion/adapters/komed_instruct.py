"""ChuGyouk/KoMedInstruct-52k 어댑터.

실제 필드(STEP 0 확인 결과): idx, output, input, instruction - Alpaca 스타일.
input이 실제로 비어있을 땐 빈 문자열이 아니라 리터럴 문자열 "<noinput>"으로 온다
(Alpaca 계열 데이터셋의 흔한 관례) - 이걸 진짜 내용으로 착각해서 content에 넣으면
안 된다.

**품질 필터 (실제 500행 표본으로 검증한 결과 기반, 추측 아님)**: 이 데이터셋은
카드 자체가 "추가 필터링 없음/환각 위험/출력 문장 불완전"을 경고하는데, 실제로
확인해보니 구체적으로 다음 패턴이 발견됐다:
- output의 45.7%가 설명을 다 쓴 뒤 "정답은: ..." 형태로 같은 내용을 한 번 더
  요약해서 덧붙인다(중복, 새 정보 없음) - RAG 청크 예산을 낭비하므로 그 뒷부분만
  제거한다(설명 본문은 그대로 보존).
- output의 0.8%가 "인공지능인 저는 신체 감각이나 감정을 경험할 수 없어서..." 같은
  자기지시적 거절 응답이다(instruction 자체가 "당신의 기분을 설명하세요" 같은
  AI에게 불가능한 요청이라 발생) - 실제 의료 지식이 전혀 없으므로 행 전체를 제외.
"""
import difflib
import re
from typing import Any

from ..schema import NormalizedRecord
from .base import DatasetAdapter

SOURCE = "KoMedInstruct-52k"
SOURCE_TYPE = "medical_instruction"

_NO_INPUT_MARKERS = {"<noinput>", "<no input>", ""}

# "정답은: ..." / "정답은 다음과 같습니다: ..." 형태로 앞서 쓴 설명을 그대로
# 반복하는 꼬리 문단 - 줄바꿈 뒤 "정답은"으로 시작하는 지점부터 전부 잘라낸다.
_ANSWER_RESTATEMENT = re.compile(r"\n\s*정답은[:：]?\s")

# "저는 AI라서 신체 감각/감정이 없다"는 식의 자기지시적 거절 - 실제 의료 지식이
# 전혀 없는 행이라 통째로 제외한다.
_AI_REFUSAL_MARKERS = (
    "인공지능인 저는",
    "AI인 저는",
    "저는 신체 감각이나 감정을",
    "감정을 경험할 수 없",
)

# input(원문)을 그대로(또는 아주 살짝만 바꿔서) output에 복붙한 경우 - 카드가
# 경고하는 "output에 해당하는 내용이 input에도 들어가는 경우"를 잡는다. 문자
# 단위 유사도가 이 정도로 높으면 새로 생성된 설명이 아니라 사실상 복사로 본다.
_LEAKAGE_SIMILARITY_THRESHOLD = 0.85


def _strip_answer_restatement(output: str) -> str:
    match = _ANSWER_RESTATEMENT.search(output)
    if not match:
        return output
    trimmed = output[: match.start()].strip()
    # 전부 "정답은..."으로 시작하는 극히 드문 경우 원본을 그대로 둔다(내용을
    # 통째로 비우지 않기 위함).
    return trimmed or output


def _is_ai_refusal(output: str) -> bool:
    return any(marker in output for marker in _AI_REFUSAL_MARKERS)


def _is_input_output_leakage(source_text: str, output: str) -> bool:
    if not source_text or not output:
        return False
    ratio = difflib.SequenceMatcher(None, source_text, output).ratio()
    return ratio >= _LEAKAGE_SIMILARITY_THRESHOLD


class KoMedInstructAdapter(DatasetAdapter):
    source = SOURCE
    source_type = SOURCE_TYPE
    hf_path = "ChuGyouk/KoMedInstruct-52k"

    def to_normalized(self, raw_row: dict[str, Any], index: int) -> NormalizedRecord | None:
        instruction = str(raw_row.get("instruction") or "").strip()
        output = str(raw_row.get("output") or "").strip()
        if not instruction or not output:
            return None

        if _is_ai_refusal(output):
            self._record("rejected_ai_refusal")
            return None

        raw_input = str(raw_row.get("input") or "").strip()
        extra_input = "" if raw_input.lower() in _NO_INPUT_MARKERS else raw_input

        if _is_input_output_leakage(extra_input or instruction, output):
            self._record("rejected_input_output_leakage")
            return None

        stripped_output = _strip_answer_restatement(output)
        if stripped_output != output:
            self._record("stripped_answer_restatement")
        output = stripped_output

        parts = [instruction]
        if extra_input:
            parts.append(extra_input)
        parts.append(output)
        content = "\n\n".join(parts)

        original_id = str(raw_row.get("idx") if raw_row.get("idx") is not None else index)

        return NormalizedRecord(
            source=SOURCE,
            source_type=SOURCE_TYPE,
            content=content,
            original_id=original_id,
            original_dataset=self.hf_path,
            title=instruction,
            answer=output,
            # 실제 HF dataset card 확인 결과 - MedInstruct-52k(합성 생성)를 DeepL로
            # 수작업 번역한 것이고, 카드 본문이 자체적으로 "추가 필터링 없음",
            # "환각(hallucination) 위험 있는 출력 다수", "출력 마지막 문장이 불완전한
            # 경우 있음"이라고 명시 경고한다. 5개 데이터셋 중 가장 신뢰도가 낮다 -
            # 팀 지시서 5-1절 "낮음" 중에서도 자체 결함 경고가 있는 경우.
            metadata={
                "language": "ko",
                "content_type": "instruction_explanation",
                "reliability": "ai_generated_unverified",
                "reliability_tier": "낮음",
                "reliability_reason": (
                    "MedInstruct-52k(합성 생성)를 DeepL로 번역, 원본 카드가 자체적으로 "
                    "'추가 필터링 없음', '환각 위험', '출력 문장 불완전 가능성'을 명시 경고함 - "
                    "실제 500행 표본 확인 결과 45.7%가 '정답은:' 중복 서술(제거함), "
                    "0.8%가 AI 자기지시 거절 응답(행 전체 제외)이었음"
                ),
                # source_tier: 1=공식기관 원문, 2=전문가 검수, 3=AI 생성(검수 없음),
                # 4=번역+합성+자체 결함 경고(이 데이터셋).
                "source_tier": 4,
                "verification_status": "translated_synthetic_unverified",
            },
        )
