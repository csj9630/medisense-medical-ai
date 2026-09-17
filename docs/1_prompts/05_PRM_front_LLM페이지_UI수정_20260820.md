# 관리자 LLM 모델 비교 UI 수정 지시문

## 1. 작업 목표

현재 `/admin` 페이지의 **LLM 탭을 모델 비교 실험 목적에 맞게 수정한다.**

현재 UI는 체크박스로 여러 모델을 선택하고 선택된 모델만 한 번에 비교하는 구조이다.

이를 다음 목적에 맞는 고정형 비교 UI로 변경한다.

### LLM 탭의 목적

1. **학습 및 파인튜닝을 완료한 메인 모델**
2. **메인 모델과 같은 계열이지만 학습이 덜 진행된 비교 모델**
3. **학습이 덜 진행된 다른 종류의 LLM**

에 동일한 질문을 입력하여 답변 결과와 실행 성능을 비교한다.

즉 단순한 모델 선택 화면이 아니라:

```text
학습 완료 메인 모델
↔ 학습이 덜 된 동일 계열 모델
↔ 학습이 덜 된 다른 LLM
```

의 차이를 확인하는 **관리자용 LLM 비교 테스트 화면**으로 만든다.

---

# 2. 이번 작업 범위

이번 작업에서는 다음만 수행한다.

```text
LLM 탭 Frontend UI 수정
LLM Mock 실행 구조 수정
모델별 실행 상태 관리
전체 모델 실행
개별 모델 실행
개별 모델 실행 취소
응답 시간 표시
Token 수 표시
반응형 UI 수정
```

이번 단계에서는 실제 AI를 연결하지 않는다.

다음 작업은 하지 않는다.

```text
FastAPI 수정
실제 Ollama 호출
실제 Gemma 실행
실제 Qwen 실행
실제 MedGemma 실행
실제 Llama 실행
Fine-tuning 모델 로딩
실제 Tokenizer 사용
Embedding
VectorDB
실제 RAG 검색
OCR 탭 수정
```

현재 Mock 구조를 이용해 UI와 실행 흐름만 구현한다.

---

# 3. 작업 전 기존 구조 분석

코드를 바로 수정하지 말고 먼저 현재 Admin Feature를 확인한다.

우선 다음 파일과 구조를 분석한다.

```text
frontend/src/features/admin/

pages/
components/
hooks/
services/
mocks/
types/
constants/
admin.css
```

특히 다음 파일을 확인한다.

```text
LlmPanel.tsx
LlmTestForm.tsx
LlmResultGrid.tsx
LlmResultCard.tsx

useLlmComparison.ts

adminAiService.ts
mockAdminAiService.ts

llmMockData.ts

types/llm.ts
adminOptions.ts
admin.css
```

기존 구조를 최대한 유지하고 불필요한 전체 리팩터링을 하지 않는다.

---

# 4. 첨부 디자인 이미지 활용 기준

첨부한 두 이미지를 다음처럼 사용한다.

### 첫 번째 이미지

목표 UI의 다음 요소를 참고한다.

```text
상단 질문 영역
전체 모델 실행 버튼
메인 모델 학습 단계 비교 영역
다른 LLM 비교 영역
모델별 독립 카드
응답 시간 및 Token 표시
```

### 두 번째 이미지

현재 프로젝트에 실제 구현된 Admin LLM 탭 디자인이다.

다음 기존 디자인 요소는 유지한다.

```text
Dark Mode
색상
Border
Radius
Typography
Admin Tab 스타일
전체적인 카드 디자인
Focus 스타일
반응형 스타일
```

첫 번째 이미지를 픽셀 단위로 그대로 복사하지 않는다.

**첫 번째 이미지의 정보 구조 + 현재 프로젝트의 디자인 시스템**

을 결합한다.

---

# 5. 현재 모델 선택 UI 제거

현재 존재하는 체크박스 기반 모델 선택 기능을 제거한다.

기존:

```text
비교 모델 2개 이상 선택

☑ MedGemma
☑ Gemma
☑ Qwen
☐ Llama
```

이 UI를 완전히 제거한다.

사용자가 모델을 체크해서 비교 대상을 선택하지 않는다.

비교 대상 모델은 화면에 항상 표시한다.

---

# 6. 새로운 기본 흐름

기존:

```text
질문 입력
→ 모델 체크박스 선택
→ 선택된 모델 비교
→ 결과 출력
```

변경:

```text
질문 입력
→ 비교 대상 모델은 항상 화면에 표시

├→ 전체 모델 비교 시작
│
└→ 원하는 모델 하나만 개별 실행

→ 각 모델별 독립 실행
→ 결과가 완료되는 순서대로 표시
```

---

# 7. LLM 탭 상단 구조

상단에는 다음만 배치한다.

```text
LLM 응답 비교

공통 질문 / Prompt

[ 질문 입력 textarea ]

[ RAG 참고 문서 선택 ]

[                전체 모델 비교 시작                ]
```

구조를 단순하게 유지한다.

---

# 8. Chunk Size / Overlap 완전 제거

LLM 탭에서는 다음 설정을 제거한다.

```text
Chunk Size
Overlap
```

둘 다 제거한다.

단순히 UI만 숨기지 말고 **LLM 비교 기능에서 더 이상 사용하지 않는다면 관련 상태와 타입도 정리한다.**

확인할 대상:

```text
LlmTestForm의 Chunk Size UI
LlmTestForm의 Overlap UI

useLlmComparison의
chunkSize 상태
overlap 상태

validation

reset 로직

LLM Mock Request

Mock fixture

결과 카드의 chunk 표시

Chunk/Overlap 전용 CSS
```

단, 기존 코드의 다른 기능에서 실제로 사용하는 값이면 무조건 삭제하지 말고 영향 범위를 먼저 확인한다.

### 중요

**OCR 탭의 Chunking 기능은 수정하지 않는다.**

OCR 탭은 RAG에 사용할 문서를 준비하는 기능이므로 Chunking 관련 기능을 그대로 유지한다.

---

# 9. RAG 참고 문서 선택 유지

현재 존재하는:

```text
[ 참고 문서 선택 ]
```

기능은 유지한다.

목적:

> 모든 모델에 동일한 RAG 참고 문서 조건을 적용해 비교하기 위한 입력

이번 단계에서는 실제 RAG 검색을 구현하지 않는다.

Mock 입력 데이터로만 처리한다.

---

# 10. 전체 모델 비교 버튼

`전체 모델 비교 시작` 버튼을 제공한다.

버튼은 **가로 전체 너비를 사용한다.**

즉:

```css
width: 100%;
```

Tailwind를 사용하는 영역이라면:

```text
w-full
```

과 동일한 의미로 구현한다.

우측에 작은 버튼 형태로 배치하지 않는다.

예상 UI:

```text
┌──────────────────────────────────────────────┐
│             전체 모델 비교 시작              │
└──────────────────────────────────────────────┘
```

---

# 11. 전체 모델 실행 동작

전체 실행 버튼 클릭 시 화면에 표시된 모든 비교 대상 모델을 실행한다.

개념적인 흐름:

```text
runAllModels()

→ Main Model 실행
→ Less-trained Main Model 실행
→ MedGemma 실행
→ Gemma 실행
→ Qwen 실행
→ Llama 실행
```

단, 실제 프로젝트에서 사용하는 모델 목록을 확인한 후 맞춘다.

모델명을 새로운 파일에 중복 하드코딩하지 않는다.

기존 constants 또는 model options가 있다면 재사용한다.

---

# 12. 전체 실행 로직과 단일 실행 로직 통합

전체 실행을 위한 완전히 별도의 실행 코드를 만들지 않는다.

다음 구조를 권장한다.

```text
runAllModels()
       ↓
각 modelId에 대해
       ↓
runModel(modelId)
```

즉:

```text
전체 실행
→ 여러 개의 단일 실행을 시작
```

하는 구조로 구현한다.

이렇게 해야 향후 Mock을 실제 API로 교체해도:

```text
전체 실행
단일 실행
취소
재실행
```

이 동일한 실행 단위를 사용할 수 있다.

---

# 13. 모델별 개별 실행 버튼

모든 모델 카드에 개별 실행 버튼을 제공한다.

Idle 상태:

```text
[ 단일 모델 응답 시작 ]
```

또는 기존 디자인에 맞춰:

```text
[ 모델 실행 ]
```

형태로 표현한다.

특정 모델을 실행하면:

```text
해당 모델만 running
→ 다른 모델 상태 유지
→ 해당 모델 Mock 응답
→ 해당 모델 결과만 갱신
```

되어야 한다.

기존 다른 모델 결과를 초기화하지 않는다.

---

# 14. 모델별 실행 취소

모델이 실행 중인 경우 실행 버튼 대신:

```text
[ 실행 취소 ]
```

버튼을 표시한다.

상태:

```text
idle
→ running
→ success
```

취소:

```text
running
→ cancelled
```

오류:

```text
running
→ error
```

로 구분한다.

---

# 15. 실제 Mock 작업 취소

취소 버튼은 UI 표시만 변경하는 가짜 취소가 되어서는 안 된다.

예를 들어:

```text
취소 클릭
→ cancelled 표시
→ 기존 setTimeout 완료
→ success로 다시 덮어쓰기
```

같은 문제가 발생하지 않도록 한다.

현재 구조에 맞게 다음과 같은 방식 중 적절한 방법을 사용한다.

```text
AbortController
clearTimeout
request ID
취소 상태 확인
```

취소된 작업의 늦게 도착한 결과가 상태를 덮어쓰지 못하게 한다.

---

# 16. 전체 실행 중 개별 취소

전체 모델 실행으로 시작된 작업이라도 개별 모델을 취소할 수 있어야 한다.

예:

```text
Main Model      completed
Comparison      running       [취소]
MedGemma        running       [취소]
Gemma           completed
Qwen            running       [취소]
Llama           error
```

한 모델을 취소하더라도 나머지 모델 실행에는 영향을 주지 않는다.

---

# 17. 모델별 독립 상태 관리

각 모델은 독립적인 실행 상태를 가진다.

예:

```ts
type LlmRunStatus = "idle" | "running" | "success" | "error" | "cancelled";
```

각 모델별로 최소 다음 정보를 관리한다.

```text
modelId
status
answer
elapsedTime
token 정보
error
```

필요하면 실행 취소를 위한 정보도 관리한다.

TypeScript `any`는 사용하지 않는다.

---

# 18. 첫 번째 비교 영역

첫 번째 영역은 **메인 모델의 학습 정도 차이 비교**이다.

제목 예:

```text
메인 모델 학습 단계 비교
```

설명:

```text
학습 및 파인튜닝을 완료한 메인 모델과
학습이 덜 진행된 동일 계열 모델의 응답 차이를 비교합니다.
```

Desktop에서는 두 카드를 나란히 배치한다.

```text
┌──────────────────────┐   ┌──────────────────────┐
│ 학습 완료 Main Model │   │ 비교용 Main Model    │
│                      │   │                      │
│ 학습 + 파인튜닝 완료 │   │ 일부 데이터 학습     │
│                      │   │                      │
│ 응답 시간            │   │ 응답 시간            │
│ Token                │   │ Token                │
│                      │   │                      │
│ 답변                 │   │ 답변                 │
│                      │   │                      │
│ [단일 실행]          │   │ [단일 실행]          │
└──────────────────────┘   └──────────────────────┘
```

---

# 19. 메인 모델 역할 Label

두 모델의 차이가 즉시 보이도록 Badge 또는 Label을 사용한다.

학습 완료 모델 예:

```text
학습 + 파인튜닝 완료
```

비교 모델 예:

```text
일부 데이터 학습
```

또는 실제 프로젝트에서 정한 학습 단계 명칭이 있으면 그것을 사용한다.

실제 학습 상태가 코드에 아직 존재하지 않는 경우에는 Mock metadata로 관리한다.

---

# 20. 두 번째 비교 영역

두 번째 영역에서는 **학습이 덜 된 다른 종류의 LLM들**을 비교한다.

제목 예:

```text
다른 LLM 비교
```

설명:

```text
동일한 질문을 학습 수준이 다른 여러 LLM에 전달하여
모델별 응답 내용과 실행 성능을 비교합니다.
```

현재 프로젝트에 존재하는 모델을 우선 사용한다.

현재 UI에서 사용되는 예:

```text
MedGemma
Gemma
Qwen
Llama
```

하지만 실제 model constants를 확인하고 기존 ID와 이름을 우선 사용한다.

---

# 21. 동일 모델 중복 여부 확인

메인 모델 비교 영역에서 사용하는 모델이 아래 다른 LLM 비교 영역에도 동일하게 포함될 수 있다.

이 경우 프로젝트 목적을 기준으로 역할을 명확하게 한다.

예:

```text
Main 영역
Qwen 학습 완료
Qwen 부분 학습

다른 LLM 영역
MedGemma 부분 학습
Gemma 부분 학습
Llama 부분 학습
```

즉 **모델 이름 자체보다 학습 상태와 비교 목적이 중요하다.**

Mock fixture에서도 각 모델의 역할을 명확히 구분한다.

---

# 22. 모델 카드 공통 정보

각 모델 카드에는 최소 다음 정보를 표시한다.

```text
모델명
학습 상태
실행 상태
응답 시간
Token 사용량
답변
개별 실행 / 취소 버튼
```

---

# 23. 응답 시간 표시

모델 실행 완료 후 각각의 응답 시간을 표시한다.

예:

```text
응답 시간
5.13 sec
```

Mock 환경에서는 실제 Mock delay 또는 fixture 값을 사용한다.

모든 모델이 동일한 시간을 표시하지 않도록 실제 비교 화면처럼 모델별 차이를 둘 수 있다.

---

# 24. Token 사용량 표시

모델마다 Token 사용량을 표시한다.

최소:

```text
총 Token
186
```

기존 타입에서 Input / Output token을 이미 사용한다면 다음처럼 표시하는 것을 권장한다.

```text
Input     72
Output   114
Total    186
```

단, 실제 tokenizer를 연결하지 않는다.

Mock fixture 값을 사용한다.

---

# 25. 결과 카드 예시

```text
┌─────────────────────────────────┐
│ Qwen                            │
│ 일부 데이터 학습                │
│                                 │
│ 상태             완료           │
│ 응답 시간         5.13 sec      │
│ Token             186           │
│                                 │
│ 답변                            │
│ ─────────────────────────────── │
│ 현재 증상만으로 정확한 진단은... │
│                                 │
│                                 │
│ [ 단일 모델 응답 시작 ]         │
└─────────────────────────────────┘
```

---

# 26. 실행 중 UI

실행 중인 모델은 Running 상태가 명확하게 보여야 한다.

예:

```text
Qwen

응답 생성 중...

Elapsed
2.3 sec

[ 실행 취소 ]
```

Spinner 또는 Skeleton을 사용할 수 있다.

기존 Admin 디자인 스타일을 유지한다.

모델 하나가 실행 중이라고 전체 페이지를 Blocking하지 않는다.

---

# 27. 완료되는 모델부터 표시

전체 실행 시 모든 모델이 완료될 때까지 기다렸다가 결과를 한 번에 표시하지 않는다.

예:

```text
Main Model       완료 → 결과 표시
Comparison       실행 중
MedGemma         완료 → 결과 표시
Gemma            실행 중
Qwen             실행 중
Llama            오류
```

처럼 각 모델의 결과가 독립적으로 업데이트되어야 한다.

---

# 28. 오류 처리

모델 하나가 오류가 발생해도 다른 모델에는 영향을 주지 않는다.

예:

```text
Llama

모델 실행 중 오류가 발생했습니다.

[ 다시 실행 ]
```

`error` 상태와 `cancelled` 상태를 구분한다.

---

# 29. 취소 상태

취소된 경우:

```text
Qwen

실행이 취소되었습니다.

[ 다시 실행 ]
```

형태로 표시한다.

취소는 오류로 표시하지 않는다.

---

# 30. 전체 실행 버튼 상태

전체 모델 실행 중에는 버튼을 적절하게 처리한다.

예:

```text
[ 전체 모델 실행 중... ]
```

중복 전체 실행 요청이 발생하지 않도록 한다.

단, 각 모델의 개별 취소 버튼은 계속 사용할 수 있어야 한다.

모든 실행이 종료되면 다시:

```text
[ 전체 모델 비교 시작 ]
```

상태로 돌아온다.

---

# 31. 입력 초기화

기존 입력 초기화 기능이 있다면 유지할 수 있다.

초기화 시 다음을 정리한다.

```text
질문
참고 문서
모델별 실행 결과
모델별 실행 상태
오류
취소 상태
```

Chunk Size / Overlap은 제거되므로 초기화 대상에서도 제외한다.

---

# 32. 중심 Hook

기존:

```text
useLlmComparison.ts
```

를 LLM 비교 기능 전체의 중심 상태 및 실행 흐름으로 유지하는 것을 우선한다.

Hook의 역할:

```text
질문 상태 관리
참고 문서 상태 관리

모델별 상태 관리

runModel(modelId)
runAllModels()
cancelModel(modelId)

reset()

Mock Service 호출
결과 취합
오류 처리
```

이 Hook을 읽으면 Frontend의 LLM 비교 실행 흐름을 이해할 수 있도록 작성한다.

---

# 33. 실행 흐름 구조

권장 구조:

```text
LlmPanel
→ useLlmComparison
→ runAllModels()

→ runModel(Main)
→ AdminAiService
← Mock Result
→ Main 상태 갱신

→ runModel(Comparison)
→ AdminAiService
← Mock Result
→ Comparison 상태 갱신

→ runModel(MedGemma)
...

→ 각각 결과 표시
```

단일 실행:

```text
LlmResultCard
→ runModel(modelId)
→ useLlmComparison
→ AdminAiService
→ mockAdminAiService
← Result
→ Hook
→ 해당 ResultCard 갱신
```

취소:

```text
LlmResultCard
→ cancelModel(modelId)
→ 실행 중인 Mock 작업 취소
→ Hook
→ cancelled 상태
→ ResultCard 갱신
```

---

# 34. Service 계층

기존 구조를 유지한다.

```text
LlmPanel
→ useLlmComparison
→ AdminAiService
→ mockAdminAiService
→ llmMockData
```

UI 컴포넌트 안에서 직접 다음을 실행하지 않는다.

```text
setTimeout
Mock answer 생성
Token 값 생성
Mock latency 결정
fixture 직접 import
```

Mock 동작은 Service와 Mock 계층에서 처리한다.

---

# 35. AdminAiService 계약 검토

기존 API 계약이 여러 모델을 한 번에 실행하는 방식이라면 단일 모델 실행에 적합하도록 변경을 검토한다.

예:

```ts
runLlmModel(request);
```

요청 개념:

```ts
interface LlmModelRequest {
  question: string;
  modelId: string;
  referenceDocument?: File | null;
}
```

응답 개념:

```ts
interface LlmModelResult {
  modelId: string;
  answer: string;
  elapsedTime: number;
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
}
```

실제 기존 타입을 먼저 확인하고 중복 타입을 만들지 않는다.

---

# 36. Mock 데이터

Mock fixture에는 모델별 비교가 가능하도록 다음 정보를 둘 수 있다.

```text
modelId
modelName
trainingStage
answer
delay
inputTokens
outputTokens
```

예:

```text
Main Model
trainingStage = fine_tuned

Comparison Model
trainingStage = partial_training
```

다른 LLM:

```text
MedGemma
Gemma
Qwen
Llama
```

각각 다른 응답 시간과 Token 값을 사용할 수 있다.

---

# 37. 예상 컴포넌트 구조

현재 구조를 우선 유지한다.

필요한 경우:

```text
features/admin/
├─ components/
│  └─ llm/
│     ├─ LlmPanel.tsx
│     ├─ LlmTestForm.tsx
│     ├─ LlmTrainingComparison.tsx
│     ├─ LlmResultGrid.tsx
│     └─ LlmResultCard.tsx
│
├─ hooks/
│  └─ useLlmComparison.ts
│
├─ services/
│  ├─ adminAiService.ts
│  └─ mockAdminAiService.ts
│
├─ mocks/
│  └─ llmMockData.ts
│
├─ types/
│  └─ llm.ts
│
├─ constants/
│  └─ adminOptions.ts
│
└─ admin.css
```

그러나 기존 컴포넌트만으로 충분하다면 불필요하게 파일을 추가하지 않는다.

---

# 38. 예상 최종 UI

```text
LLM 응답 비교

같은 질문과 동일한 참고 문서 조건으로
각 모델의 응답 결과와 성능 지표를 비교합니다.


공통 질문 / Prompt

┌──────────────────────────────────────────────┐
│ 두통이 있습니다.                            │
│                                              │
└──────────────────────────────────────────────┘

[ RAG 참고 문서 선택 ]
답변 근거로 사용할 문서를 지정합니다.


┌──────────────────────────────────────────────┐
│             전체 모델 비교 시작              │
└──────────────────────────────────────────────┘



메인 모델 학습 단계 비교

학습 완료 모델과 부분 학습 모델의 차이를 비교합니다.

┌────────────────────────┐ ┌────────────────────────┐
│ Main Model             │ │ Comparison Model       │
│ 학습 + 파인튜닝 완료    │ │ 일부 데이터 학습       │
│                        │ │                        │
│ 응답 시간       5.1s   │ │ 응답 시간       8.4s   │
│ Token          154     │ │ Token          181     │
│                        │ │                        │
│ 답변 ...               │ │ 답변 ...               │
│                        │ │                        │
│ [단일 모델 실행]       │ │ [단일 모델 실행]       │
└────────────────────────┘ └────────────────────────┘



다른 LLM 비교

┌────────────────────────┐ ┌────────────────────────┐
│ MedGemma               │ │ Gemma                  │
│ 일부 데이터 학습       │ │ 일부 데이터 학습       │
│                        │ │                        │
│ 응답 시간       6.4s   │ │ 응답 시간       9.1s   │
│ Token          186     │ │ Token          154     │
│ 답변 ...               │ │ 답변 ...               │
│ [단일 모델 실행]       │ │ [단일 모델 실행]       │
└────────────────────────┘ └────────────────────────┘

┌────────────────────────┐ ┌────────────────────────┐
│ Qwen                   │ │ Llama                  │
│ 일부 데이터 학습       │ │ 일부 데이터 학습       │
│                        │ │                        │
│ 응답 시간              │ │ 응답 시간              │
│ Token                  │ │ Token                  │
│ 답변 ...               │ │ 답변 ...               │
│ [단일 모델 실행]       │ │ [단일 모델 실행]       │
└────────────────────────┘ └────────────────────────┘
```

---

# 39. 반응형

Desktop:

```text
메인 비교 모델: 2열

다른 모델: 2열 또는 현재 Content 폭에 맞는 Grid
```

작은 화면:

```text
Main Model
↓
Comparison Model
↓
MedGemma
↓
Gemma
↓
Qwen
↓
Llama
```

형태로 변경한다.

고정 width를 남발하지 않는다.

Flex/Grid를 사용한다.

---

# 40. 기존 Admin 디자인 유지

기존 스타일을 최대한 재사용한다.

다음 디자인을 유지한다.

```text
Dark Mode
기존 Admin 배경
Border
Radius
Typography
Accent Color
Focus Visible
Status 표현
Responsive breakpoint
```

새로운 UI를 만들기 위해 프로젝트 전체 디자인 시스템을 수정하지 않는다.

---

# 41. 접근성

기존 Admin UI의 접근성 구조를 유지한다.

확인 항목:

```text
button의 disabled 상태
aria-busy
aria-live
focus-visible
키보드 접근
상태가 색상에만 의존하지 않는지
```

실행, 취소, 다시 실행 버튼은 문구만 보더라도 기능을 이해할 수 있어야 한다.

---

# 42. OCR 탭 수정 금지

이번 작업에서는 OCR 탭을 수정하지 않는다.

특히 다음 기능은 그대로 유지한다.

```text
파일 업로드
문서 분석 테스트
OCR 결과
Chunk 결과
VectorDB 저장 테스트
```

LLM 탭에서 Chunk Size / Overlap을 제거하는 것과 OCR의 Chunking 기능은 별개이다.

---

# 43. Backend 수정 금지

이번 작업에서는 다음을 수정하지 않는다.

```text
backend/
ai/
DB schema
FastAPI Router
환경변수
Ollama
```

Frontend Mock 단계까지만 구현한다.

---

# 44. 코드 주석

상태 관리나 취소 처리처럼 초심자가 이해하기 어려운 주요 코드에는 필요한 경우 한국어 주석을 추가한다.

예:

```text
전체 모델 실행이 개별 runModel()을 호출하는 이유

모델별 실행 상태가 분리된 이유

취소된 요청의 늦은 응답을 무시하는 처리

Mock Service와 UI를 분리한 이유
```

코드 자체를 그대로 읽어주는 불필요한 주석은 작성하지 않는다.

---

# 45. 검증 항목

작업 후 반드시 확인한다.

## UI

```text
모델 체크박스가 완전히 제거되었는가

Chunk Size가 제거되었는가

Overlap이 제거되었는가

RAG 참고 문서 선택은 유지되는가

전체 모델 비교 버튼이 width 100%인가

모든 비교 대상 모델이 항상 화면에 표시되는가

각 모델 카드에 개별 실행 버튼이 있는가
```

## 전체 실행

```text
전체 실행 시 모든 모델이 실행되는가

각 모델이 독립적으로 running 상태가 되는가

완료된 모델부터 결과가 표시되는가

모든 모델의 응답 시간이 동일하지 않아도 정상 처리되는가
```

## 개별 실행

```text
한 모델만 실행할 수 있는가

다른 모델 결과가 유지되는가

완료된 모델을 다시 실행할 수 있는가
```

## 취소

```text
실행 중인 모델에 취소 버튼이 표시되는가

특정 모델만 취소할 수 있는가

취소가 다른 모델 실행에 영향을 주지 않는가

취소된 Mock 결과가 나중에 success로 덮어쓰이지 않는가

취소한 모델을 다시 실행할 수 있는가
```

## 결과

모든 완료 모델에서 다음을 확인한다.

```text
모델명
학습 상태
응답 상태
응답 시간
Token 수
답변
```

---

# 46. 빌드 검증

현재 프로젝트에 존재하는 실제 script를 먼저 확인한 후 실행한다.

최소:

```text
TypeScript type check
Vite production build
```

기존 프로젝트에 lint/test script가 없다면 존재하는 것처럼 만들어서 보고하지 않는다.

검증하지 않은 항목을 통과했다고 작성하지 않는다.

---

# 47. 작업 완료 문서

프로젝트에 제공된 공통 작업 문서화 지침을 따른다.

작업 완료 후 실제 최종 코드를 기준으로:

```text
docs/02_LLM_비교_UI_수정_YYYY-MM-DD.md
```

형태의 설명 문서를 작성한다.

이미 `02` 번호를 사용하는 다른 문서가 있다면 기존 `docs` 번호 체계를 먼저 확인하고 충돌하지 않게 조정한다.

문서에는 최소 다음 내용을 포함한다.

```text
작업 목적

변경 전 구조

변경 후 구조

UI 변경 내용

모델 그룹 구성

전체 모델 실행 흐름

단일 모델 실행 흐름

실행 취소 흐름

중심 Hook 설명

Service / Mock 구조

모델별 상태 관리

응답 시간 및 Token 처리

수정 파일별 역할

코드 읽는 순서

검증 결과

현재 Mock인 부분

향후 실제 FastAPI/LLM 연동 시 교체 지점
```

실제 LLM 연결이 되어 있지 않다는 사실을 명확히 작성한다.

---

# 48. 기존 코드 변경 최소화

이번 변경을 위해 관련 없는 코드를 수정하지 않는다.

피해야 할 것:

```text
프로젝트 전체 리팩터링

Admin 구조 전체 변경

OCR 코드 변경

Router 변경

MainLayout 변경

기존 Theme 변경

새 상태관리 라이브러리 추가

불필요한 dependency 설치

관련 없는 formatting 대량 변경
```

현재 LLM 비교 Feature에 필요한 파일만 수정한다.

---

# 49. 최종 실행 흐름

최종적으로 Frontend에서는 다음 구조가 되어야 한다.

```text
질문 입력
→ 필요하면 RAG 참고 문서 선택
→ 전체 모델 비교 시작

→ useLlmComparison.runAllModels()

→ runModel(Main Model)
→ runModel(Less-trained Main Model)
→ runModel(MedGemma)
→ runModel(Gemma)
→ runModel(Qwen)
→ runModel(Llama)

→ 각각 AdminAiService 호출
→ 각각 Mock 결과 반환
→ 각각 중심 Hook으로 복귀
→ 모델별 상태/시간/Token/답변 갱신
→ ResultCard 표시
```

개별 실행:

```text
모델 카드
→ 단일 모델 실행
→ runModel(modelId)
→ AdminAiService
→ Mock
← 결과 반환
→ Hook
→ 해당 모델 카드만 갱신
```

취소:

```text
실행 중 모델
→ 실행 취소
→ cancelModel(modelId)
→ 해당 요청 중단
→ cancelled
→ 해당 카드만 갱신
```

---

# 50. 핵심 요구사항 요약

최종적으로 반드시 충족해야 하는 요구사항은 다음과 같다.

```text
1. 모델 체크박스 선택 제거

2. 모든 비교 모델을 화면에 항상 표시

3. 학습 완료 메인 모델과
   학습이 덜 된 동일 계열 모델을 비교

4. 학습이 덜 된 다른 LLM들도 별도 영역에서 비교

5. Chunk Size 제거

6. Overlap 제거

7. RAG 참고 문서 선택 유지

8. 전체 모델 비교 시작 버튼 제공

9. 전체 모델 비교 버튼 width: 100%

10. 각 모델별 단일 실행 버튼 제공

11. 모델마다 독립적인 실행 상태 관리

12. 모델 실행 중 개별 취소 버튼 제공

13. 전체 실행 중에도 개별 모델 취소 가능

14. 모델별 응답 시간 표시

15. 모델별 Token 사용량 표시

16. 완료되는 모델부터 결과 표시

17. 한 모델 오류/취소가 다른 모델에 영향 주지 않음

18. Mock 데이터만 사용

19. OCR 탭 수정 금지

20. Backend 수정 금지

21. 기존 Admin 디자인 및 Dark Mode 유지

22. 현재 Admin Feature 아키텍처 최대한 유지

23. 작업 후 공통 문서화 지침에 따라 docs 문서 작성
```

## 최종 목표

이 화면은 더 이상:

```text
사용자가 모델을 골라 실행하는 화면
```

이 아니라,

**미리 정해진 실험 대상 모델을 동일 조건에서 반복 실행하면서 학습 수준 및 모델 종류에 따른 답변 품질과 실행 성능을 비교하는 관리자용 LLM Comparison Lab**

이 되어야 한다.
