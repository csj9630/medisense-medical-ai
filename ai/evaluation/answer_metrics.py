"""정답 답변과 모델 답변을 비교하는 Framework 독립 성능지표입니다."""

import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher

TOKEN_PATTERN = re.compile(r"[가-힣]+|[a-z0-9]+")


def normalize_answer(text: str) -> str:
    """대소문자·Unicode·연속 공백 차이를 제거한 비교 문자열을 만듭니다."""

    normalized = unicodedata.normalize("NFKC", text).lower()
    return " ".join(normalized.split())


def exact_match(expected: str, predicted: str) -> float:
    """정규화한 두 답변이 완전히 같으면 1.0을 반환합니다."""

    return 1.0 if normalize_answer(expected) == normalize_answer(predicted) else 0.0


def token_f1(expected: str, predicted: str) -> float:
    """한국어·영문·숫자 Token의 중복 개수를 반영한 F1을 계산합니다."""

    expected_tokens = TOKEN_PATTERN.findall(normalize_answer(expected))
    predicted_tokens = TOKEN_PATTERN.findall(normalize_answer(predicted))
    if not expected_tokens or not predicted_tokens:
        return 1.0 if expected_tokens == predicted_tokens else 0.0

    common_count = sum((Counter(expected_tokens) & Counter(predicted_tokens)).values())
    if common_count == 0:
        return 0.0
    precision = common_count / len(predicted_tokens)
    recall = common_count / len(expected_tokens)
    return 2 * precision * recall / (precision + recall)


def character_similarity(expected: str, predicted: str) -> float:
    """표현이 조금 다른 답변도 확인할 수 있도록 문자 시퀀스 유사도를 계산합니다."""

    expected_text = normalize_answer(expected)
    predicted_text = normalize_answer(predicted)
    if not expected_text or not predicted_text:
        return 1.0 if expected_text == predicted_text else 0.0
    return SequenceMatcher(None, expected_text, predicted_text).ratio()
