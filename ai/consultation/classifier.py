"""증상 텍스트 → 진료과 분류. 시스템 프롬프트(prompts/system_prompt.md)의 "# 2. 입력 정보"가
요구하는 `[진료과 분류 결과]`(추천 진료과 + 신뢰도 라벨)를 만든다.

지금은 키워드 매칭 규칙 기반이다 — 정교한 분류 모델은 아직 없다. 이래도 괜찮은 이유는
프롬프트 쪽에 이미 안전장치가 있기 때문이다: 신뢰도가 "낮음"이면 LLM이 특정 진료과를
확정적으로 안내하지 않도록 프롬프트가 강제한다. 즉 이 분류기가 틀리거나 애매해도,
최악의 경우 "여러 진료과에서 평가할 수 있다"는 안전한 답변으로 떨어질 뿐이다.

나중에 임베딩 유사도 기반이나 파인튜닝된 분류 모델로 교체하려면 `BaseQueryClassifier`
Protocol만 만족하면 된다 — 호출하는 쪽(`pipeline.py`)은 구현체를 몰라도 된다.
"""
import re
from dataclasses import dataclass
from typing import Literal, Protocol

ConfidenceLabel = Literal["높음", "중간", "낮음"]


@dataclass(frozen=True)
class DepartmentResult:
    department: str | None
    confidence: ConfidenceLabel
    # 디버깅/평가용 — 실제 프롬프트에는 안 들어간다.
    matched_keywords: tuple[str, ...] = ()


class BaseQueryClassifier(Protocol):
    def classify(self, query: str) -> DepartmentResult: ...


# 진료과별 키워드 — 순서는 우선순위와 무관하고, 매칭 개수로만 판단한다.
# 흔한 증상 위주로만 우선 채웠다. 실제 오분류 사례가 쌓이면 이 표를 계속 보강할 것.
_DEPARTMENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "내과": (
        "복통", "배가 아", "속이 아", "설사", "변비", "소화", "메스꺼", "구토",
        "발열", "열이", "기침", "가래", "속쓰림", "위염", "위산", "당뇨", "고혈압",
    ),
    # 2026-09 실측(라이브 채팅 테스트)으로 추가 - 가슴/심장 관련 표현이 어떤 진료과에도
    # 안 걸려서 department=None(화면 표시상 "기타")으로 떨어지는 공백이 있었다. 흉통
    # 중 응급 수준(가슴 쥐어짜듯이 아픔 등)은 risk_detector.py가 별도로 하드 필터링해
    # LLM 호출 자체를 건너뛰므로, 여기 키워드는 그 정도까지는 아닌 흉부/순환기 증상을
    # 잡기 위한 것이다 - 응급 필터를 놓친 케이스의 2차 방어선이기도 하다.
    "순환기내과": (
        "두근거림", "두근두근", "심장이 뛰", "심장 두근", "가슴 두근", "부정맥",
        "가슴이 뻐근", "가슴 답답", "흉통", "가슴 통증", "가슴이 아",
    ),
    "이비인후과": (
        "목이 아", "인후통", "콧물", "코막힘", "코피", "중이염", "귀가 아", "귀 통증",
        "어지럼", "어지러", "이명", "목소리", "쉰 목소리", "편도",
    ),
    "피부과": (
        "발진", "두드러기", "가려움", "가렵", "피부", "여드름", "습진", "아토피",
        "물집", "붉은 반점", "탈모",
    ),
    "정형외과": (
        "허리", "무릎", "관절", "골절", "삐끗", "어깨", "고개", "근육통",
        "디스크", "손목", "발목", "결림", "결려", "뻐근",
    ),
    "신경과": (
        "두통", "머리가 아", "저림", "마비", "떨림", "경련", "어지러움", "시야",
        "언어장애", "기억력",
    ),
    "안과": (
        "눈이 아", "시력", "눈 충혈", "눈물", "안구건조", "눈이 침침", "안압",
        "눈 통증", "눈에 통증", "눈이 피로", "눈 피로", "눈이 뻑뻑",
    ),
    "산부인과": ("생리", "월경", "임신", "질염", "하복부 통증(여성)"),
    "비뇨의학과": ("배뇨", "소변", "혈뇨", "전립선", "요로감염"),
    "정신건강의학과": ("불안", "우울", "불면", "잠이 안", "공황", "스트레스"),
    "소아청소년과": ("아기가", "영유아", "신생아", "소아"),
}


def _normalize(text: str) -> str:
    """공백을 없애고 매칭한다 — "배가 아"(키워드)가 "배가아파서"(실제 입력, 띄어쓰기
    없이 쓰는 경우가 많다)에도 걸리게 하기 위함. 원래 클래스 docstring은 "공백을
    무시한다"고 되어있었지만 실제로는 그냥 substring 매칭이라 안 걸리는 버그가 있었다."""
    return re.sub(r"\s+", "", text)


class KeywordDepartmentClassifier:
    """공백/조사를 무시한 단순 부분 문자열 매칭. 형태소 분석 없이 최소 구현으로 시작한다."""

    def classify(self, query: str) -> DepartmentResult:
        text = query.strip()
        if not text:
            return DepartmentResult(department=None, confidence="낮음")

        normalized_text = _normalize(text)
        scores: dict[str, list[str]] = {}
        for department, keywords in _DEPARTMENT_KEYWORDS.items():
            hits = [kw for kw in keywords if _normalize(kw) in normalized_text]
            if hits:
                scores[department] = hits

        if not scores:
            return DepartmentResult(department=None, confidence="낮음")

        ranked = sorted(scores.items(), key=lambda item: len(item[1]), reverse=True)
        top_department, top_hits = ranked[0]

        # 2등과 매칭 개수가 같으면(=여러 진료과가 동시에 그럴듯함) 확정하지 않는다.
        tied_with_second = len(ranked) > 1 and len(ranked[1][1]) == len(top_hits)
        if tied_with_second:
            return DepartmentResult(department=top_department, confidence="중간", matched_keywords=tuple(top_hits))

        confidence: ConfidenceLabel = "높음" if len(top_hits) >= 2 else "중간"
        return DepartmentResult(department=top_department, confidence=confidence, matched_keywords=tuple(top_hits))


def get_default_classifier() -> BaseQueryClassifier:
    return KeywordDepartmentClassifier()
