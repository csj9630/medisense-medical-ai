# Admin LLM Backend Mock 전환 결과 보고서

## 1. 작업 목적

관리자 LLM Comparison Lab의 답변, 지연 시간, Token, 오류 더미 데이터를 Frontend에서 생성하지 않고 FastAPI Backend에서 생성해 HTTP로 수신하도록 전환했다.

Frontend는 질문·모델·참고 문서명을 전달하고 모델별 UI 상태만 관리한다. 이 구조는 향후 Backend Mock을 실제 Ollama 또는 LLM Provider 호출로 교체할 때 Frontend 계약을 유지하기 위한 단계다.

## 2. 변경 전 구조

```text
LlmResultCard
→ useLlmComparison
→ AdminAiService
→ mockAdminAiService
→ llmMockData
→ Frontend에서 답변·지연·Token 생성
```

Frontend 내부에 모델별 답변, delay, Output Token, Llama 오류 fixture가 존재했다. Backend 서버를 실행하지 않아도 LLM 비교 UI는 동작했지만 실제 API 경계와 오류 응답을 검증할 수 없었다.

## 3. 변경 후 구조

```text
LlmResultCard
→ useLlmComparison.runModel(modelId)
→ AdminAiService.runLlmModel()
→ apiAdminAiService
→ POST /api/admin/llm/run
→ FastAPI Admin Router
→ admin_llm.run_model()
→ Backend Mock fixture
→ HTTP 응답
→ 해당 모델 카드 갱신
```

Frontend의 `mockAdminAiService.ts`, `llmMockData.ts`는 삭제했다. 모델 그룹, 표시 이름, 학습 상태와 같은 UI metadata는 Frontend 상수에 남아 있지만 실행 결과 더미 데이터는 포함하지 않는다.

## 4. 단일 모델 실행 API

### Endpoint

```text
POST /api/admin/llm/run
```

### Request

```json
{
  "prompt": "의료 문서의 핵심 내용을 요약해 주세요.",
  "modelId": "main-fine-tuned",
  "documentName": "reference.pdf"
}
```

| 필드 | 형식 | 설명 |
| --- | --- | --- |
| `prompt` | string | 모든 모델에 적용할 공통 질문 |
| `modelId` | string | 단일 실행할 모델 ID |
| `documentName` | string 또는 null | Mock RAG 조건에 사용할 참고 문서명 |

참고 문서 파일 자체는 이번 단계에서 업로드하거나 읽지 않는다.

### Success Response

```json
{
  "modelId": "main-fine-tuned",
  "answer": "Backend에서 생성한 Mock 답변",
  "responseTimeSeconds": 1.25,
  "inputTokens": 75,
  "outputTokens": 214,
  "totalTokens": 289
}
```

### Error Response

| 상황 | HTTP 상태 | 설명 |
| --- | --- | --- |
| 미지원 모델 | 422 | 지원 모델 ID 검증 실패 |
| Llama Mock Provider 오류 | 503 | 모델별 부분 오류 UI 검증 |

한 모델에서 503 오류가 발생해도 `runAllModels()`의 `Promise.allSettled()` 구조로 인해 다른 모델 실행은 계속된다.

## 5. Backend Mock 모델 구성

Backend의 `LLM_RUN_FIXTURES`가 모델별 답변, 지연 시간, Output Token, 오류 여부를 관리한다.

| Model ID | 지연 | Output Token | 결과 |
| --- | ---: | ---: | --- |
| `main-fine-tuned` | 1.25초 | 214 | 성공 |
| `main-partial` | 2.05초 | 168 | 성공 |
| `medgemma` | 1.60초 | 186 | 성공 |
| `gemma` | 2.35초 | 154 | 성공 |
| `qwen` | 1.85초 | 203 | 성공 |
| `llama` | 2.65초 | 0 | HTTP 503 오류 |

모델마다 지연 시간이 다르므로 전체 실행 시 완료되는 모델부터 Frontend 카드가 갱신된다.

## 6. 응답 시간과 Token 생성

Backend는 `time.perf_counter()`로 Mock 요청의 실제 서버 처리 시간을 측정한다.

```text
Input Token
= 질문 길이를 이용한 Mock 계산
+ 참고 문서명이 있으면 Mock 가산값

Output Token
= 모델별 Backend fixture

Total Token
= Input Token + Output Token
```

실제 Tokenizer는 아직 사용하지 않는다. Frontend는 서버가 반환한 값을 가공 없이 모델 카드에 표시한다.

## 7. 실행 취소 흐름

Frontend의 모델별 `AbortController` 구조는 유지했다.

```text
모델 실행 취소
→ AbortController.abort()
→ fetch의 AbortSignal 전달
→ HTTP 요청 수신 중단
→ 요청 버전 무효화
→ 해당 카드 cancelled
```

요청 버전 검증으로 취소되거나 재실행된 이전 요청의 응답이 현재 카드 상태를 덮어쓰지 않는다. 한 모델 취소는 다른 모델 요청에 영향을 주지 않는다.

현재 Backend Mock은 상태를 저장하지 않는 단순 요청·응답 구조다. 실제 LLM Provider 연결 시에는 HTTP 연결 중단뿐 아니라 Provider 추론 취소 지원 여부도 별도로 확인해야 한다.

## 8. 기존 API 호환성

기존 API는 삭제하지 않았다.

```text
POST /api/admin/llm/compare
```

기존 다중 모델 비교 계약과 `compare_models()`는 다른 팀원의 기존 호출을 위해 유지한다. 새 Admin LLM UI만 단일 실행 API `/llm/run`을 사용한다.

## 9. Service 경계

Frontend의 `AdminAiService` 계약은 다음처럼 유지된다.

```text
analyzeDocument() → FastAPI OCR
saveDocument()    → FastAPI 저장 Mock
runLlmModel()     → FastAPI LLM Backend Mock
```

`adminAiService`는 다시 `apiAdminAiService` 하나를 사용한다. UI와 Hook에는 Endpoint URL, JSON 변환, HTTP 오류 처리 코드가 노출되지 않는다.

## 10. 삭제된 Frontend Mock 파일

| 파일 | 삭제 이유 |
| --- | --- |
| `frontend/src/features/admin/mocks/llmMockData.ts` | 답변·지연·Token fixture를 Backend로 이동 |
| `frontend/src/features/admin/services/mockAdminAiService.ts` | Frontend Mock 타이머와 결과 생성 제거 |

## 11. 수정 파일별 역할

| 파일 | 역할 |
| --- | --- |
| `backend/app/schemas/admin.py` | 단일 모델 요청·응답 Pydantic 계약 |
| `backend/app/api/admin/router.py` | `POST /llm/run` Endpoint |
| `backend/app/services/admin_llm.py` | 모델 검증, delay, 답변, Token, 오류 생성 |
| `backend/tests/test_admin_llm.py` | Service 및 HTTP API 계약 테스트 |
| `frontend/src/features/admin/services/adminAiService.ts` | LLM을 포함한 공통 API Service 연결 |
| `frontend/src/features/admin/services/apiAdminAiService.ts` | `/admin/llm/run` HTTP 변환 및 AbortSignal 전달 |
| `frontend/src/features/admin/components/llm/LlmPanel.tsx` | `Backend Mock` 상태 표시 |
| `docs/2_reports/07_RPT_AdminLLM_비교UI수정_20260820.md` | 후속 Backend 전환 문서 안내 추가 |

## 12. 코드 읽는 순서

1. `frontend/src/features/admin/hooks/useLlmComparison.ts`
2. `frontend/src/features/admin/services/adminAiService.ts`
3. `frontend/src/features/admin/services/apiAdminAiService.ts`
4. `backend/app/api/admin/router.py`
5. `backend/app/schemas/admin.py`
6. `backend/app/services/admin_llm.py`
7. `backend/tests/test_admin_llm.py`

## 13. 검증 결과

### Backend 신규 테스트

```text
backend/.venv/Scripts/python.exe -m unittest tests.test_admin_llm
```

- 4개 테스트 통과
- Backend 성공 결과 및 Token 합계 확인
- 미지원 모델 422 확인
- Llama Mock 오류 503 확인
- HTTP camelCase 응답 계약 확인

### Backend 전체 테스트

```text
backend/.venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py"
```

- 총 35개 테스트 통과
- 기존 OCR 및 Job 테스트 통과

FastAPI TestClient 실행 중 Starlette의 `httpx` 사용 방식에 대한 Deprecation Warning이 출력됐지만 테스트 실패나 현재 API 동작 오류는 아니다.

### Frontend 빌드

```text
npm.cmd run build
```

- TypeScript `tsc --noEmit` 통과
- Vite production build 통과
- 변환 모듈 1,877개

### 정적 검증

- `git diff --check` 통과
- Frontend 답변·지연·Token fixture 참조 없음
- `/admin/llm/run` Frontend·Backend 계약 연결 확인
- 기존 `/admin/llm/compare` 유지 확인

## 14. 현재 Mock인 부분

- Backend 모델별 답변
- 모델별 지연 시간
- Input/Output/Total Token
- Llama Provider 오류
- 참고 문서 조건

UI metadata를 제외한 실행 결과 더미 데이터는 모두 Backend에서 생성한다.

## 15. 향후 실제 LLM 교체 지점

실제 모델을 연결할 때 Frontend와 `/api/admin/llm/run` 계약은 유지하고 Backend의 `run_model()` 내부를 Provider Adapter 호출로 교체한다.

```text
현재
run_model()
→ Backend fixture
→ asyncio.sleep()
→ Mock Response

향후
run_model()
→ LlmProvider.generate()
→ Ollama 또는 실제 모델 서버
→ 실제 Token 및 응답 시간
```

실제 연동 단계에서는 Provider timeout, 동시 실행 수 제한, 추론 취소, 모델 목록 설정화, 의료 답변 안전 정책을 추가로 검토해야 한다.
