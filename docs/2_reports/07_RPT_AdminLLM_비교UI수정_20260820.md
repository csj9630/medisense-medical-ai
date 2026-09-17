# Admin LLM 비교 UI 수정 결과 보고서

> 후속 변경: LLM Mock 생성 위치는 `08_RPT_AdminLLM_BackendMock전환_20260820.md` 작업에서 Backend로 이전했다. 이 문서는 최초 Frontend Mock UI 구현 시점의 구조를 기록한다.

## 1. 작업 목적

관리자 `/admin` 페이지의 LLM 탭을 사용자가 비교 모델을 선택하는 화면에서, 미리 정한 모델들을 동일 조건으로 반복 실행하며 학습 단계와 모델 종류에 따른 응답 및 성능 차이를 확인하는 `LLM Comparison Lab`으로 변경했다.

이번 작업은 Frontend Mock 범위만 다룬다. 실제 FastAPI LLM API, Ollama, 실제 모델, Tokenizer, Embedding, VectorDB, RAG 검색은 연결하지 않았다. Backend와 OCR 탭은 수정하지 않았다.

## 2. 변경 전 구조

```text
질문 입력
→ 체크박스로 모델 2개 이상 선택
→ Chunk Size / Overlap 입력
→ 여러 모델을 한 요청으로 실행
→ 모든 결과를 한 번에 표시
```

기존 구조에서는 모델별 실행·취소·재실행이 불가능했고, 한 모델의 상태를 다른 모델과 독립적으로 관리하지 않았다. 참고 문서는 실제 파일 업로드 없이 파일명만 요청 상태에 포함했다.

## 3. 변경 후 구조

```text
질문 입력
→ 필요하면 공통 RAG 참고 문서 선택
→ 비교 대상 모델 6개를 항상 표시

├─ 전체 모델 비교 시작
│  └─ runModel(modelId) 6개 병렬 실행
│
└─ 카드별 모델 실행
   └─ 선택한 모델의 상태만 변경

→ 완료되는 카드부터 결과 표시
→ 실행 중인 카드만 개별 취소 가능
```

LLM 탭의 모델 체크박스, Chunk Size, Overlap과 관련 상태·타입·결과 표시는 모두 제거했다. OCR 탭의 Chunk 설정은 그대로 유지했다.

## 4. UI 변경 내용

상단 입력 영역은 다음 요소로 단순화했다.

```text
공통 질문 / Prompt
RAG 참고 문서 선택
전체 모델 비교 시작
입력 및 결과 초기화
```

`전체 모델 비교 시작` 버튼은 입력 카드의 전체 너비를 사용한다. 모델 실행 중에는 중복 전체 실행을 막고, 각 모델 카드의 실행 취소 버튼은 계속 사용할 수 있다.

결과 영역은 다음 두 그룹으로 구성했다.

1. 메인 모델 학습 단계 비교
2. 다른 LLM 비교

Desktop에서는 각 그룹을 2열 Grid로 표시하고 640px 이하에서는 1열로 전환한다. 기존 Admin 색상, 카드 Border, Radius, Focus 스타일과 Dark Mode 변수를 재사용했다.

## 5. 모델 그룹 구성

### 메인 모델 학습 단계 비교

| ID | 표시 이름 | 학습 상태 |
| --- | --- | --- |
| `main-fine-tuned` | Main Model | 학습 + 파인튜닝 완료 |
| `main-partial` | Comparison Model | 일부 데이터 학습 |

두 모델은 같은 프로젝트 메인 모델 계열이라는 Mock metadata를 사용한다.

### 다른 LLM 비교

기존 `MODEL_OPTIONS`를 재사용해 모델명 중복 선언을 피했다.

| ID | 표시 이름 | 역할 |
| --- | --- | --- |
| `medgemma` | medgemma | 외부 비교 모델 |
| `gemma` | gemma | 외부 비교 모델 |
| `qwen` | Qwen | 외부 비교 모델 |
| `llama` | Llama | 오류 상태 검증용 Mock 포함 |

## 6. 전체 모델 실행 흐름

```text
LlmTestForm
→ useLlmComparison.runAllModels()
→ LLM_COMPARISON_MODEL_IDS 순회
→ runModel(modelId)
→ executeModel(modelId)
→ AdminAiService.runLlmModel()
→ mockAdminAiService.runLlmModel()
→ 모델별 완료 순서대로 해당 카드 갱신
```

`Promise.allSettled()`를 사용하므로 한 모델의 오류나 취소가 다른 모델 실행을 중단하지 않는다. 전체 실행을 위한 별도 모델 처리 로직을 만들지 않고 단일 실행 함수 `runModel()`을 재사용한다.

## 7. 단일 모델 실행 흐름

```text
LlmResultCard
→ 모델 실행 또는 다시 실행
→ runModel(modelId)
→ 해당 모델만 running
→ Mock 결과 수신
→ 해당 모델만 success 또는 error
```

다른 카드의 이전 결과와 상태는 유지된다. 완료·오류·취소된 모델은 다시 실행할 수 있다.

## 8. 실행 취소 흐름

각 실행마다 모델 ID별 `AbortController`를 생성한다.

```text
실행 취소
→ 해당 모델 AbortController.abort()
→ Mock delay의 setTimeout 제거
→ 해당 모델 cancelled
→ 다른 모델은 계속 실행
```

모델별 요청 버전도 함께 관리한다. 취소 또는 재실행된 이전 요청에서 늦은 결과가 도착하더라도 현재 요청 버전과 다르면 상태를 갱신하지 않는다. 따라서 취소 상태가 나중에 success로 덮어써지지 않는다.

## 9. 중심 Hook

`useLlmComparison.ts`가 다음 상태와 흐름을 관리한다.

- 공통 질문
- 공통 참고 문서
- 모델별 실행 상태 Map
- 전체 실행 상태
- 입력 검증 오류
- `runModel(modelId)`
- `runAllModels()`
- `cancelModel(modelId)`
- `reset()`

초기화 시 실행 중인 모든 Controller를 중단하고 요청 버전을 무효화한 뒤 질문, 참고 문서, 모델 상태, 오류를 초기값으로 되돌린다.

## 10. Service 및 Mock 구조

```text
LlmPanel
→ useLlmComparison
→ AdminAiService
→ mockAdminAiService
→ llmMockData
```

OCR은 기존 `apiAdminAiService`를 계속 사용한다. LLM만 취소 가능한 Frontend Mock 실행으로 분리했다.

UI 컴포넌트는 Mock delay, 답변, Token 값을 직접 알지 않는다. 모델별 Mock 답변·지연·출력 Token·오류 여부는 `llmMockData.ts`에 있고, 실제 타이머와 결과 생성은 `mockAdminAiService.ts`가 담당한다.

## 11. 모델별 상태 관리

```ts
type LlmRunStatus =
  | "idle"
  | "running"
  | "success"
  | "error"
  | "cancelled";
```

각 모델은 다음 정보를 독립적으로 가진다.

- Model ID
- 실행 상태
- 답변 또는 오류
- 시작 시각 및 응답 시간
- Input Token
- Output Token
- Total Token

실행 중에는 시작 시각을 기준으로 Elapsed 시간을 갱신한다.

## 12. 응답 시간 및 Token 처리

Mock Service는 `performance.now()`를 기준으로 실제 Mock 대기 시간을 측정해 응답 시간을 반환한다. 모델별 fixture의 delay가 다르므로 완료 순서와 응답 시간이 다르다.

Input Token은 질문 길이와 참고 문서 선택 여부를 이용한 Mock 계산값이다. Output Token은 모델별 fixture이며 Total Token은 두 값을 합산한다. 실제 Tokenizer는 사용하지 않는다.

## 13. 수정 파일별 역할

| 파일 | 역할 |
| --- | --- |
| `components/llm/LlmPanel.tsx` | 입력 폼, 고정 비교 결과 영역 연결 |
| `components/llm/LlmTestForm.tsx` | 질문, 참고 문서, 전체 실행, 초기화 UI |
| `components/llm/LlmResultGrid.tsx` | 메인 학습 단계 및 다른 LLM 그룹 배치 |
| `components/llm/LlmResultCard.tsx` | 모델 상태, 지표, 답변, 실행·취소·재실행 UI |
| `hooks/useLlmComparison.ts` | 모델별 상태 및 전체 실행·단일 실행·취소 흐름 |
| `services/adminAiService.ts` | 실제 OCR API와 LLM Mock의 공통 UI 계약 |
| `services/apiAdminAiService.ts` | 기존 실제 OCR 호출 유지 |
| `services/mockAdminAiService.ts` | 취소 가능한 단일 LLM Mock 실행 |
| `mocks/llmMockData.ts` | 모델별 답변, 지연, Token, 오류 fixture |
| `types/llm.ts` | 모델 metadata, 요청·결과·실행 상태 타입 |
| `constants/adminOptions.ts` | 고정 비교 모델과 두 그룹 정의 |
| `admin.css` | 고정 카드 Grid, 상태, 반응형, Dark Mode 스타일 |

## 14. 코드 읽는 순서

1. `constants/adminOptions.ts`
2. `types/llm.ts`
3. `hooks/useLlmComparison.ts`
4. `services/adminAiService.ts`
5. `services/mockAdminAiService.ts`
6. `mocks/llmMockData.ts`
7. `components/llm/LlmPanel.tsx`
8. `components/llm/LlmTestForm.tsx`
9. `components/llm/LlmResultGrid.tsx`
10. `components/llm/LlmResultCard.tsx`
11. `admin.css`

## 15. 검증 결과

### 자동 검증

```text
npm.cmd run build
```

- TypeScript `tsc --noEmit`: 통과
- Vite production build: 통과
- 변환 모듈: 1,879개
- `git diff --check`: 통과
- Backend 및 `ai/` 변경사항 없음
- LLM 컴포넌트·Hook·타입에서 Chunk Size, Overlap, 체크박스 선택 흔적 없음
- OCR Chunk 관련 코드는 그대로 유지

### 로컬 서버 확인

- Vite 개발 서버 실행 성공
- `http://127.0.0.1:5173/admin`: HTTP 200
- Root HTML 확인 성공

내장 브라우저 제어 런타임이 초기화 중 종료되어 이번 작업에서는 실제 클릭과 스크린샷 기반 시각 검증을 완료하지 못했다. 따라서 반응형 배치와 상호작용은 TypeScript 빌드, CSS breakpoint, 상태 전이 코드 기준으로 검증했으며 실제 브라우저 수동 확인이 추가로 필요하다.

## 16. 현재 Mock인 부분

- 모델 실행
- 모델별 답변
- 응답 지연
- Input/Output/Total Token
- Llama 오류
- RAG 참고 문서 조건

참고 문서는 실제 업로드하거나 읽지 않는다. 선택한 파일명과 선택 여부만 Mock 답변 및 Input Token 조건에 사용한다.

## 17. 향후 실제 FastAPI 및 LLM 연동 교체 지점

실제 LLM을 연결할 때 UI와 Hook의 모델별 상태 구조는 유지하고 `AdminAiService.runLlmModel()` 구현만 교체하는 것이 기본 방향이다.

```text
현재
AdminAiService.runLlmModel
→ mockAdminAiService

향후
AdminAiService.runLlmModel
→ apiAdminAiService
→ FastAPI 단일 모델 실행 API
→ 실제 LLM Provider
```

실제 API도 요청별 `AbortSignal`, 모델별 부분 오류, 응답 시간, Token 값을 지원해야 전체 실행·단일 실행·취소 UI 계약을 그대로 유지할 수 있다.
