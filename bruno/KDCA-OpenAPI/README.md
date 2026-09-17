# 질병관리청 공공데이터 OpenAPI - Bruno 컬렉션

현재 상태: **2026-09-03, 67개 엔드포인트 실제 등록 및 저장 완료.** 처음엔 골격만
있었고(공공데이터포털의 일반적인 serviceKey/pageNo/numOfRows 패턴으로 추측), 실제
토큰과 목록을 받아서 확인해보니 그 추측과 다른 API였습니다(`TOKEN`/`cntntsSn`
파라미터, XML 응답) - `00 TEMPLATE...bru`가 실제 형태로 갱신되어 있습니다.

## 왜 이 폴더가 `backend/bruno`와 분리되어 있나

`backend/bruno`는 우리 백엔드 API(localhost:8000)를 테스트하는 컬렉션이고, 이건
**외부** 질병관리청 서버(api.kdca.go.kr)를 직접 호출하는 별개 컬렉션이라 분리했습니다.

## 실제 연결 지점

- 엔드포인트 레지스트리(67개 질환/증상 이름 + cntntsSn): `data/kdca_endpoints.yaml`
- 실제 fetch + 정제 + 청킹 + 임베딩 + Neon 저장 어댑터:
  `ai/rag/ingestion/adapters/kdca_openapi.py`
- 실행 CLI(다른 5개 HF 데이터셋과 동일한 진입점):
  ```
  python scripts/rag_ingest.py --source kdca-openapi --dry-run   # 저장 없이 확인만
  python scripts/rag_ingest.py --source kdca-openapi             # 실제 Neon 저장
  ```
  `.env`의 `KDCA_HEALTHINFO_TOKEN`이 필요합니다(export해서 실행).

## Bruno는 언제 쓰나

새 엔드포인트를 등록하기 전에 응답 구조를 눈으로 먼저 확인하고 싶을 때
`00 TEMPLATE...bru`를 열어서 `environments/Local.bru`의 `token`만 채우고
직접 호출해보면 됩니다 - `cntntsSn` 값만 바꿔서 다른 질환도 확인할 수 있습니다.
