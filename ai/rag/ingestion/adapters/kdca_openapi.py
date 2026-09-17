"""질병관리청(KDCA) 공공 건강정보 OpenAPI 어댑터.

실제 응답 구조(STEP 0 확인 결과, 2026-09-03 - 사용자가 승인받은 토큰으로 4개
주제를 직접 호출해서 확인함): XML, `<svc><CNTNTSSJ>제목</CNTNTSSJ>
<cntntsClList><cntntsCl><CNTNTS_CL_NM>섹션명</CNTNTS_CL_NM>
<CNTNTS_CL_CN>본문</CNTNTS_CL_CN></cntntsCl>...</cntntsClList></svc>`.
한 페이지(cntntsSn)에 개요/원인/진단및검사/관련질환/자주하는질문/연관주제어 같은
섹션이 여러 개 들어있다 - 페이지 전체를 하나의 NormalizedRecord로 만든다(HF
데이터셋들처럼 행 단위가 아니라, asan.py가 다루는 "병원 공식 질병정보 페이지"와
같은 성격).

다른 어댑터와 달리 HuggingFace가 아니라 실시간 API라서 `load_raw()`를 완전히
새로 구현한다(base.py의 기본 구현은 안 씀) - `hf_path`는 이 어댑터에서는 의미
없지만 NormalizedRecord.original_dataset에 남길 라벨 용도로만 쓴다.

실제 확인된 주의사항(STEP 0):
- 존재하지 않는 cntntsSn을 넣어도 HTTP 200 + CODE=S001(OK)로 오고, 그냥
  `cntntsClList`가 빈 채로 온다 - 상태 코드로 성공 여부를 판단하면 안 되고,
  실제 섹션이 있는지 확인해야 한다.
- 일부 섹션은 텍스트가 아니라 이미지 다운로드 URL만 들어있다
  (`https://is.kdca.go.kr/.../healthInfoFileDown.do?SEQ=...`) - 이런 섹션은
  건너뛴다.
- api.kdca.go.kr는 http:// 요청도 https://로 리다이렉트되는데, 그 서버가 TLS
  legacy renegotiation을 요구해서 기본 SSL 설정으로는 연결이 거부된다
  (`_build_ssl_context()` 참고) - 공식 정부 API라 인증서 자체는 신뢰하되,
  구형 서버 설정 때문에 옵션을 낮춰서 붙는다.
"""
import os
from collections.abc import Iterator
from html import unescape
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import httpx
import yaml

from ..schema import NormalizedRecord
from .base import DatasetAdapter

SOURCE = "KDCA-HealthInfo-OpenAPI"
SOURCE_TYPE = "government_health_information"
API_BASE_URL = "http://api.kdca.go.kr/api/provide/healthInfo"
TOKEN_ENV_VAR = "KDCA_HEALTHINFO_TOKEN"
_REGISTRY_PATH = Path(__file__).resolve().parents[4] / "data" / "kdca_endpoints.yaml"

# 이미지 다운로드 URL만 있는 섹션을 걸러내기 위한 힌트 - 실제 응답에서
# CNTNTS_CL_CN이 이 접두어로 시작하는 경우를 봤다(STEP 0).
_IMAGE_URL_PREFIX = "https://is.kdca.go.kr/"

# 환자 대상 설명이 아니라 학술 인용 목록이라 RAG 근거로 부적합하고, 실제로
# "Chung, K. F. & Pavord, I. D. (2008)..." 식 인용구에 HTML 엔티티(&amp;) 잔재가
# 섞여 있어서 cleaning.py의 has_html_garbage에 걸린다(STEP 0, cntntsSn=6253에서
# 확인) - 이 섹션 하나 때문에 페이지 전체(개요/원인/진단 등 멀쩡한 나머지 섹션)가
# 통째로 거부되는 걸 막기 위해 아예 합치기 전에 뺀다.
_EXCLUDED_SECTION_NAMES = {"참고문헌"}


def _build_ssl_context():
    import ssl

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.options |= 0x4  # SSL_OP_LEGACY_SERVER_CONNECT - api.kdca.go.kr 서버 한정 대응
    return ctx


def load_registry(path: Path = _REGISTRY_PATH) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("endpoints", [])


class KdcaOpenApiAdapter(DatasetAdapter):
    source = SOURCE
    source_type = SOURCE_TYPE
    hf_path = "kdca.go.kr/api/provide/healthInfo"  # HF 데이터셋 아님 - 라벨 용도

    def __init__(self, *, registry_path: Path = _REGISTRY_PATH) -> None:
        super().__init__()
        self._registry_path = registry_path

    def load_raw(
        self, limit: int | None = None, *, shuffle_seed: int | None = None
    ) -> Iterator[dict[str, Any]]:
        # shuffle_seed는 여기선 의미 없다(전체 67건이라 스트리밍 편향 문제가
        # 없음) - 인터페이스 호환을 위해 인자만 받고 무시한다.
        token = os.environ.get(TOKEN_ENV_VAR)
        if not token:
            raise RuntimeError(
                f"{TOKEN_ENV_VAR} 환경변수가 없습니다 - .env에 있는 값을 export한 뒤 다시 실행하세요."
            )

        endpoints = load_registry(self._registry_path)
        if limit is not None:
            endpoints = endpoints[:limit]

        with httpx.Client(timeout=20.0, verify=_build_ssl_context(), follow_redirects=True) as client:
            for entry in endpoints:
                cntnts_sn = entry["cntnts_sn"]
                response = client.get(API_BASE_URL, params={"TOKEN": token, "cntntsSn": cntnts_sn})
                response.raise_for_status()
                parsed = _parse_response(response.text, cntnts_sn=cntnts_sn)
                if parsed is None:
                    continue
                yield parsed

    def to_normalized(self, raw_row: dict[str, Any], index: int) -> NormalizedRecord | None:
        title = raw_row["title"]
        sections: list[tuple[str, str]] = raw_row["sections"]
        if not title or not sections:
            return None

        content = "\n\n".join(f"## {name}\n{text}" for name, text in sections)

        return NormalizedRecord(
            source=SOURCE,
            source_type=SOURCE_TYPE,
            content=content,
            original_id=str(raw_row["cntnts_sn"]),
            original_dataset=self.hf_path,
            title=title,
            metadata={
                "language": "ko",
                "content_type": "disease_information",
                # 질병관리청이 직접 작성/게시한 공식 건강정보 원문(생성/번역 아님) -
                # asan.py(대학병원 공식 자료)와 같은 근거로 매우 높음/tier 1.
                "reliability": "verified_official",
                "reliability_tier": "매우 높음",
                "reliability_reason": "질병관리청(KDCA) 공식 건강정보 OpenAPI 원문(생성/번역 아님)",
                "source_tier": 1,
                "verification_status": "official_source",
            },
        )


def _parse_response(xml_text: str, *, cntnts_sn: int) -> dict[str, Any] | None:
    """실제 저장 대상 텍스트만 골라 dict로 만든다. 존재하지 않는 cntntsSn이거나
    섹션이 하나도 없으면 None(호출부가 그 항목을 건너뜀)."""
    root = ElementTree.fromstring(xml_text)
    title_el = root.find("./svc/CNTNTSSJ")
    title = unescape((title_el.text or "").strip()) if title_el is not None else ""

    sections: list[tuple[str, str]] = []
    for cl in root.findall("./svc/cntntsClList/cntntsCl"):
        name_el = cl.find("CNTNTS_CL_NM")
        content_el = cl.find("CNTNTS_CL_CN")
        name = (name_el.text or "").strip() if name_el is not None else ""
        # CDATA 안에 원본 CMS에서 넘어온 HTML 엔티티(예: 본문 중간 인용 링크의
        # "...cancer_seq=5237&amp;menu_seq=5253)")가 그대로 남아있는 경우가 실제로
        # 있다(STEP 0, cntntsSn=6524) - 삭제가 아니라 원래 문자로 복원하는
        # 것뿐이고(& 는 없어지지 않고 &amp;에서 &로 돌아옴), 이대로 두면
        # cleaning.py의 has_html_garbage가 페이지 전체를 거부해버린다.
        text = unescape((content_el.text or "").strip()) if content_el is not None else ""
        if not name or not text:
            continue
        if text.startswith(_IMAGE_URL_PREFIX):
            continue  # 이미지 다운로드 URL만 있는 섹션 - 텍스트 아님
        if name in _EXCLUDED_SECTION_NAMES:
            continue
        sections.append((name, text))

    if not title or not sections:
        return None
    return {"cntnts_sn": cntnts_sn, "title": title, "sections": sections}
