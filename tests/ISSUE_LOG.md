# 테스트 이슈 로그

`tests/`(코드 유닛테스트, `test_*.py`)와는 별개로, **실제 서비스(dev-thegpt-project.thegpt.workers.dev)를
직접 써보면서 발견한 문제**와 그에 대한 조치를 기록하는 문서. 루트의 `ISSUE_LOG.md`와
같은 성격이며, 이 파일은 "RAG + 임베딩 + LLM 응답 품질" / "진료과 자동분류" QA에
집중한다. 세션: 2026-09-10.

## `test_*.py` 파일에 대해

`tests/` 아래 `test_*.py`는 전부 실제 자동화 유닛테스트다(임시로 만든 확인용 스크립트가
아니다). `unittest discover`로 CI/개발 중 계속 돌리는 정식 테스트 코드이며, 이 로그에서
언급하는 수정마다 대응하는 회귀 테스트를 같이 추가했다 — 아래 표의 "테스트"란 참고.

## 1. 라이브 QA 테스트로 발견한 문제

관리자 계정(`admin@admin.com`)으로 개발계 채팅에 직접 여러 질문을 넣어보고, 관리자
대시보드 지표(성공률 30%/49건, 폴백 응답 28%, RAG 검색 성공률 83%)로 교차 검증.

| # | 문제 | 재현 예시 | 원인 | 조치 | 상태 |
|---|---|---|---|---|---|
| 1-1 | 심근경색 의심 증상(흉통+식은땀+팔 저림)이 응급 안내 없이 무관한 답변("거즈로 상처를 눌러주세요")으로 나감 | "가슴 한가운데가 쥐어짜듯이 아프고 식은땀이 나면서 왼쪽 팔까지 저려요" | `risk_detector.py`의 다단어 키워드 갭 정규식이 6자까지만 허용해서 "가슴"+"한가운데가"+"쥐어짜"(7자 갭)를 못 잡음 | 갭을 15자로 확대(`_KEYWORD_GAP`) | ✅ [ai/consultation/risk_detector.py](../ai/consultation/risk_detector.py) |
| 1-2 | 위 대화 및 뇌졸중 의심 대화 모두 진료과가 "기타"로 집계됨 | 1-1과 동일 + "갑자기 오른쪽 팔다리에 힘이 안 들어가고 말이 어눌해졌어요"(이건 응급 안내는 정상 작동) | (a) `classifier.py`에 순환기내과 카테고리 자체가 없었음 (b) `pipeline.py`가 응급 감지 시 `department=None`을 강제해서, 분류 가능한 경우도 버려짐 | (a) 순환기내과 카테고리 추가 (b) 응급 분기에서도 `classify()` 실행하도록 변경 | ✅ [classifier.py](../ai/consultation/classifier.py) / [pipeline.py](../ai/consultation/pipeline.py) |
| 1-3 | 피부 발진 질문 답변에 사용자가 언급 안 한 "홍채 부종" 환각, 마크다운 파편(`\`, 홑 `*`), 빈 대괄호 `[ ]` 잔존 | "얼굴에 갑자기 붉은 두드러기가 올라오고 심하게 가려워요" | 소형 파인튜닝 모델(MedGemma 4B LoRA) 자체의 생성 불안정성으로 보임 | 보류(TODO, 아래 "남은 과제" 참고) — 근본 해결은 파인튜닝 데이터/디코딩 파라미터 쪽 | ⚠️ 미해결 |
| 1-4 | 편도염 질문에 의료 답변 대신 메타 지시문만 출력됨("답변 완료 후에는 새로운 프롬프트와 함께 다시 시작하십시오...") | "목이 3일째 심하게 아프고 편도가 부어서 침도 삼키기 힘들어요" | `response_validator.py`에 이런 "완전 비-답변" 패턴을 걸러낼 필터가 없었음 | `_looks_like_non_answer()` 추가 — 감지되면 빈 문자열 반환, `pipeline.py`가 `FALLBACK_ANSWER`로 대체 | ✅ [response_validator.py](../ai/consultation/response_validator.py) |
| 1-5 | 답변이 항상 한 줄로 쭉 나옴(줄바꿈 없음) | 전반적 | `system_prompt.md`가 "여러 항목이어도 하나의 문단 안에서" 쓰라고 명시 | 내용 단위(증상 요약/원인/위험신호/자가관리/병원안내)로 문단을 나누고 빈 줄로 구분하도록 지시 변경 | ✅ [prompts/system_prompt.md](../ai/consultation/prompts/system_prompt.md) |

## 2. 진료과 분류 방식 재검토

사용자 질문: "RAG 검색 결과 재활용을 주로 사용하고, 애매하면 LLM이 분류하는 걸로
바꾸면 어때?" → 구현 전 실행 가능성부터 확인.

| # | 확인 내용 | 결과 |
|---|---|---|
| 2-1 | RAG 청크에 진료과(department) 메타데이터가 실제로 얼마나 채워져 있는지 | 어댑터 7개 중 `snuh_clinical_qa` 단 1개만 채움(원본 category 필드 번역) — 나머지 6개는 원본에 카테고리 필드 자체가 없어서 빈 리스트. "RAG 우선"을 그대로 적용하면 대부분 질문에서 신호가 없어 실효성이 낮음 |
| 2-2 | 원본에 카테고리가 없는 데이터셋도 department를 채울 수 있는지 | 데이터셋마다 다름 - `genmed_gpt`(의사-환자 대화)는 답변 텍스트에 진료과가 직접 언급되는 경우가 있어 추출 가능. `komed_instruct`/`health_search_qa`는 카테고리도 텍스트 언급도 없어서 분류기로 "추정"하는 방법뿐 → 이건 발명이 아니라 추론이라 성격이 다르므로 정책 결정 필요(보류) |
| 2-3 | 실제 조치 | `genmed_gpt.py` 어댑터에 답변 텍스트 기반 진료과 추출 추가(`generated_metadata=True`로 구분). `ai/consultation/context.derive_department_from_chunks()` 신설 — RAG 청크의 department를 다수결로 집계해 분류 신호로 재활용. **우선순위**: 사전 분류가 이미 "높음" 확신이면 유지(RAG가 무관한 문서를 끌어온 사례가 실제로 있어서, 강한 신호를 약한 신호로 덮어쓰지 않게 보수적으로 둠) → 그 외엔 RAG 문서 태그 우선 → 그래도 없으면 기존 키워드 분류 |
| 2-4 | 곁가지로 발견한 버그 | "순환기내과"가 "내과"를 부분 문자열로 포함해서, 진료과명 추출 로직(`extract_mentioned_department` 계열)이 "순환기내과" 언급을 "내과+순환기내과 둘 다 걸림 = 모호함"으로 오판하는 문제 발견 → 더 구체적인(긴) 이름 우선하도록 수정 | ✅ [response_validator.py](../ai/consultation/response_validator.py), [genmed_gpt.py](../ai/rag/ingestion/adapters/genmed_gpt.py) |

## 3. 테스트 현황

```
python -B -m unittest discover -s tests -t . -p "test_*.py" -v
```
- 258개 중 252개 통과. 실패 6개는 전부 `tests/ai/ocr/*`, `tests/smoke/test_paddle_ocr.py` —
  이번 세션에서 건드리지 않은 OCR 모듈이 `cv2`/`PIL`(Pillow)/paddleocr 미설치로 임포트
  자체가 실패하는 **환경 문제**다(이 세션은 이 라이브러리들이 없는 bare Python으로
  실행함 — `backend/.venv` 없이 시스템 python 사용). 오늘 수정한 `ai/consultation`,
  `ai/rag` 관련 테스트는 전부 통과.
- 오늘 추가한 회귀 테스트: `test_classifier.py`, `test_pipeline.py`, `test_risk_detector.py`,
  `test_response_validator.py`, `test_context.py`(이상 `tests/ai/consultation/`),
  `test_adapters.py`(`tests/ai/rag/ingestion/`).

## 남은 과제 (TODO)

- [ ] 1-3(피부과 답변 환각/마크다운 파편)은 아직 대응 필터가 없음 — 새로 관찰되는 정확한
      패턴이 나오면 `response_validator.py`에 추가.
- [ ] `komed_instruct`/`health_search_qa` 등 카테고리 없는 데이터셋의 department를
      분류기로 "추정"해서 채울지는 정책 결정 필요(`ai/rag/ingestion/CLAUDE.md` 참고).
- [ ] `kdca_openapi`(67건, "관련질환" 섹션 보유)의 질환명→진료과 매핑은 시도 안 함 —
      자유 텍스트에서 질환명을 안정적으로 뽑아내는 작업이 선행돼야 해서 후순위로 미룸.
- [ ] 오늘 수정 사항은 로컬 코드에만 반영됨(브랜치 `kbg`) — 실제 배포에는 커밋/배포 필요.
