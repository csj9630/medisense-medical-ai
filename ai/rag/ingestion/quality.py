"""의료 정보 신뢰성 관련 플래그. 내용을 고치거나 걸러내지 않는다 - 사람이 나중에
검토할 수 있도록 표시만 남긴다(needs_review). 데이터를 임의로 "고쳐서" 새로운
의료정보를 만들어내는 것보다, 있는 그대로 두고 표시하는 쪽이 안전하다는 팀 스펙
원칙을 그대로 따른다.
"""
import re

# 용량/처방/응급/확진처럼 잘못 전달되면 위험한 내용이 섞인 chunk를 사람이 우선
# 검토할 수 있도록 표시하기 위한 키워드. 완벽한 목록이 아니라 "일단 걸리면 사람이
# 한 번 보게" 하는 보수적인 신호일 뿐이다.
_NEEDS_REVIEW_PATTERN = re.compile(
    r"(용량|처방|투여|수술\s*적응|응급|긴급|확진|진단\s*기준|가이드라인|금기|부작용)"
)


def detect_needs_review(text: str) -> bool:
    return bool(_NEEDS_REVIEW_PATTERN.search(text))
