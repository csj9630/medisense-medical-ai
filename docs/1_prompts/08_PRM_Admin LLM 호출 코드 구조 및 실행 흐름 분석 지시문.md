# Admin LLM 호출 코드 구조 및 실행 흐름 분석 지시문

## 1. 작업 목적

현재 프로젝트에서 `/admin` 페이지의 **LLM 탭에서 모델을 실행했을 때 실제 코드가 어떤 순서로 동작하는지 분석하고 초심자가 이해하기 쉽게 설명한다.**

이번 작업의 목적은 코드 수정이나 기능 구현이 아니다.

**현재 존재하는 코드를 읽고 실행 흐름을 이해하기 위한 분석만 수행한다.**

따라서 이번 작업에서는 다음을 하지 않는다.

```text
코드 수정
리팩터링
새 파일 생성
API 구현
FastAPI 수정
Mock을 실제 LLM으로 교체
UI 수정
타입 변경
라이브러리 설치
```

---

# 2. 가장 알고 싶은 내용

Admin LLM 탭에서 사용자가 다음과 같은 동작을 했을 때:

```text
질문 입력
→ 전체 모델 비교 시작
```

또는:

```text
질문 입력
→ 특정 모델 단일 실행
```

실제 코드가 어떤 파일과 함수를 거쳐 실행되는지 분석한다.

최종적으로 다음 질문에 답할 수 있어야 한다.

```text
버튼 클릭은 어느 컴포넌트에서 시작되는가?

어떤 함수가 가장 먼저 호출되는가?

전체 실행을 관리하는 중심 함수는 무엇인가?

단일 모델 실행을 관리하는 함수는 무엇인가?

React 상태는 어디에서 관리되는가?

Service는 어떤 역할을 하는가?

Mock 데이터는 어디에서 만들어지는가?

실행 결과가 어떤 경로로 다시 돌아오는가?

결과가 어느 컴포넌트에서 화면에 출력되는가?

실행 취소는 어떤 방식으로 이루어지는가?

전체 실행과 단일 실행은 어떤 관계인가?
```

---

# 3. 반드시 실제 현재 코드를 기준으로 분석

과거 문서나 예상 구조만 보고 설명하지 않는다.

현재 저장소의 실제 코드를 직접 확인한다.

특히 다음 영역을 우선 탐색한다.

```text
frontend/src/features/admin/
```

예상되는 주요 영역:

```text
pages/
components/
hooks/
services/
mocks/
types/
constants/
```

실제 파일명이 예상과 다르다면 현재 코드 기준으로 설명한다.

---

# 4. 우선 확인할 파일

실제 존재 여부를 확인한 뒤 다음 계열의 파일을 우선 분석한다.

```text
AdminPage

LlmPanel
LlmTestForm
LlmResultGrid
LlmResultCard

useLlmComparison

adminAiService
mockAdminAiService

llmMockData

LLM 관련 types
LLM 관련 constants
```

다른 파일이 LLM 실행에 관여한다면 함께 추적한다.

---

# 5. 가장 먼저 전체 실행 흐름을 한 줄로 정리

세부 설명 전에 현재 실제 코드를 기준으로 전체 흐름을 먼저 보여준다.

예상 형태:

```text
사용자 버튼 클릭
→ LlmPanel
→ useLlmComparison
→ runModel()
→ AdminAiService
→ MockAdminAiService
→ Mock 데이터 생성
→ Result 반환
→ useLlmComparison
→ React State 갱신
→ LlmResultCard 재렌더링
```

단, 위 흐름을 그대로 사용하지 말고 **실제 현재 코드에서 확인한 함수와 파일 이름으로 작성한다.**

---

# 6. 전체 모델 실행 흐름 분석

`전체 모델 비교 시작` 버튼을 눌렀을 때의 흐름을 별도로 분석한다.

다음 형태로 단계별로 설명한다.

```text
1. 사용자가 버튼 클릭
2. 어떤 onClick handler가 실행됨
3. 어떤 Hook 함수가 호출됨
4. 전체 모델 목록을 어디에서 가져오는지 확인
5. 모델별 실행 함수를 어떻게 호출하는지 확인
6. Service 호출
7. Mock 실행
8. 모델별 결과 반환
9. 상태 갱신
10. 화면 렌더링
```

실제 구현이 다음과 같은 관계인지도 확인한다.

```text
runAllModels()
→ runModel(modelA)
→ runModel(modelB)
→ runModel(modelC)
...
```

만약 다른 구조라면 실제 구현을 설명한다.

---

# 7. 단일 모델 실행 흐름 분석

각 모델 카드의:

```text
단일 모델 실행
```

버튼을 눌렀을 때도 별도로 추적한다.

예상 설명 형태:

```text
LlmResultCard
→ onRun(modelId)
→ LlmPanel
→ useLlmComparison.runModel(modelId)
→ AdminAiService
→ Mock Service
→ 결과 반환
→ 해당 modelId의 상태만 갱신
→ 해당 ResultCard 다시 렌더링
```

실제 코드 기준으로 작성한다.

---

# 8. 전체 실행과 단일 실행의 관계 설명

초심자가 특히 이해하기 쉽게 다음을 설명한다.

예:

```text
전체 실행과 단일 실행이 완전히 다른 기능인지

아니면

전체 실행이 내부적으로 단일 실행 함수를 여러 번 호출하는 구조인지
```

가능하다면 다음처럼 설명한다.

```text
전체 실행
   ↓
runAllModels()

   ├→ runModel(A)
   ├→ runModel(B)
   ├→ runModel(C)
   └→ runModel(D)
```

현재 코드가 이런 구조가 아니라면 실제 구조를 사용한다.

---

# 9. 중심 Hook 설명

LLM 실행 상태를 관리하는 중심 Hook이 있다면 가장 중요하게 설명한다.

예:

```text
useLlmComparison
```

이 Hook에서 무엇을 관리하는지 실제 코드를 기준으로 정리한다.

예:

```text
질문
참고 문서
모델별 실행 상태
모델별 결과
응답 시간
Token 수
오류
취소 상태
전체 실행 여부
```

그리고 어떤 함수가 존재하는지 설명한다.

예:

```text
runModel()
runAllModels()
cancelModel()
reset()
```

실제 함수 이름을 사용한다.

---

# 10. 중심 함수 표시

전체 흐름을 이해하기 위해 **가장 먼저 읽어야 할 중심 함수**를 명확하게 알려준다.

예:

```text
중심 Hook:
useLlmComparison()

중심 실행 함수:
runModel()

전체 실행 함수:
runAllModels()
```

그리고 왜 이 함수를 중심으로 보면 되는지 설명한다.

---

# 11. 데이터가 이동하는 방향 설명

각 단계에서 어떤 데이터가 이동하는지 보여준다.

예:

```text
사용자 입력

question
referenceDocument
modelId
```

↓

```text
runModel()

modelId
question
referenceDocument
```

↓

```text
AdminAiService
```

↓

```text
Mock Response

modelId
answer
elapsedTime
inputTokens
outputTokens
totalTokens
```

↓

```text
React State
```

↓

```text
LlmResultCard
```

실제 타입을 확인하여 현재 사용하는 필드 이름으로 작성한다.

---

# 12. TypeScript 타입 설명

LLM 관련 Request / Response / State 타입을 찾아 설명한다.

예:

```ts
LlmModelRequest
LlmModelResult
LlmRunStatus
```

각 타입에 대해:

```text
어디에서 생성되는가
어디로 전달되는가
어디에서 사용되는가
```

를 설명한다.

단순히 타입 필드 목록만 나열하지 않는다.

---

# 13. Service 계층 설명

다음 관계를 초심자가 이해하기 쉽게 설명한다.

예:

```text
React Component
→ Hook
→ AdminAiService
→ MockAdminAiService
```

특히:

> 왜 Component가 Mock Service를 직접 호출하지 않고 중간에 AdminAiService를 거치는가?

를 설명한다.

예를 들어 현재 구조가 실제 API 교체를 위한 추상화라면:

```text
현재

Hook
→ AdminAiService
→ Mock 구현체
```

향후:

```text
Hook
→ AdminAiService
→ FastAPI 구현체
```

로 교체할 수 있다는 관계를 설명한다.

단, 현재 코드에서 실제로 확인되는 내용만 단정한다.

---

# 14. Mock 동작 설명

현재 LLM이 실제 모델을 실행하는지 반드시 확인한다.

Mock이라면:

```text
Mock 결과는 어느 파일에 있는가?

응답 내용은 어디에서 가져오는가?

응답 시간은 어떻게 만들어지는가?

Token 수는 어떻게 만들어지는가?

setTimeout 또는 Promise delay가 어디에 있는가?

모델별 오류 fixture가 있는가?
```

를 설명한다.

실제 LLM이라고 오해할 수 없도록 명확하게 구분한다.

---

# 15. 현재 실제 네트워크 호출 여부 확인

Admin LLM 실행 과정에서 다음이 실제로 존재하는지 검색한다.

```text
fetch
axios
apiClient
/api/
FastAPI endpoint
Ollama URL
HTTP request
```

그리고 결과를 명확하게 설명한다.

예:

```text
현재 LLM 비교 기능에서는 네트워크 요청이 발생하지 않는다.

LlmPanel
→ Hook
→ Mock Service

까지만 실행된다.
```

또는 실제 API가 이미 연결되어 있다면 그 흐름을 설명한다.

추측하지 않는다.

---

# 16. 모델 실행 상태 설명

각 모델의 상태가 어디에서 어떻게 관리되는지 분석한다.

예:

```text
idle
running
success
error
cancelled
```

각 상태가 언제 바뀌는지 설명한다.

예:

```text
실행 전
idle

runModel()
↓
running

Mock 결과 정상 반환
↓
success

오류
↓
error

사용자 취소
↓
cancelled
```

실제 코드에 존재하는 상태만 사용한다.

---

# 17. 취소 기능 흐름 분석

모델 실행 중:

```text
실행 취소
```

버튼을 눌렀을 때 실제 흐름을 별도로 설명한다.

다음 내용을 확인한다.

```text
취소 버튼은 어느 Component에 있는가?

cancel 함수는 어디에 있는가?

AbortController를 사용하는가?

clearTimeout을 사용하는가?

request ID 방식인가?

취소된 뒤 늦게 돌아온 결과를 어떻게 무시하는가?

한 모델 취소가 다른 모델 실행에 영향을 주는가?
```

실제 코드를 따라가며 설명한다.

---

# 18. React State 변경과 재렌더링 설명

초심자가 React 흐름도 이해할 수 있도록 다음을 설명한다.

예:

```text
Mock Service가 결과를 직접 화면에 그리는 것이 아니다.

Mock Service
→ Result 반환
→ Hook에서 setState
→ React가 상태 변경 감지
→ ResultCard 재렌더링
```

실제 코드의 state 변수와 setter가 있다면 이름을 함께 보여준다.

---

# 19. Props 전달 흐름 설명

Component 사이에서 데이터와 함수가 어떤 식으로 내려가는지 분석한다.

예:

```text
LlmPanel
    ↓ props
LlmResultGrid
    ↓ props
LlmResultCard
```

데이터:

```text
model
result
status
```

Callback:

```text
onRun
onCancel
```

형태로 나뉘어 있다면 이를 설명한다.

---

# 20. "데이터는 아래로, 이벤트는 위로" 관점 설명

현재 구조가 이에 해당한다면 초심자에게 다음 개념을 연결하여 설명한다.

```text
데이터
Hook → Panel → Grid → Card

사용자 이벤트
Card → callback → Hook
```

즉:

```text
상태 데이터 ↓

사용자 이벤트 ↑
```

형태로 설명한다.

---

# 21. 파일별 역할 표 작성

최종 설명에는 다음 형식의 표를 반드시 포함한다.

| 순서 | 파일 | 주요 함수/컴포넌트 | 역할 |
|---:|---|---|---|
| 1 | `LlmPanel.tsx` | `LlmPanel` | LLM 비교 UI 조립 |
| 2 | `useLlmComparison.ts` | `runModel()` | 단일 모델 실행 흐름 관리 |
| 3 | `adminAiService.ts` | `...` | Service 계약 |
| 4 | `mockAdminAiService.ts` | `...` | Mock 실행 |
| 5 | `llmMockData.ts` | `...` | Mock fixture |
| 6 | `useLlmComparison.ts` | state update | 결과 저장 |
| 7 | `LlmResultCard.tsx` | `LlmResultCard` | 결과 출력 |

위 내용은 예시이므로 **실제 코드에 존재하는 파일과 함수만 사용한다.**

---

# 22. 실제 실행 순서를 번호로 정리

예:

```text
[전체 모델 비교]

1. 사용자가 전체 모델 비교 버튼을 클릭한다.
2. LlmTestForm의 callback이 실행된다.
3. useLlmComparison의 runAllModels()가 호출된다.
4. runAllModels()가 각 모델에 대해 runModel()을 실행한다.
5. runModel()이 모델 상태를 running으로 변경한다.
6. AdminAiService를 호출한다.
7. Mock Service가 일정 시간 후 Mock 결과를 반환한다.
8. runModel()으로 결과가 돌아온다.
9. Hook이 해당 모델의 state를 success로 변경한다.
10. React가 ResultCard를 다시 렌더링한다.
```

실제 현재 코드를 기준으로 작성한다.

---

# 23. 함수 호출 후 어디로 돌아오는지 강조

이번 분석에서 가장 중요하게 설명할 부분 중 하나다.

다음 형태로 표시한다.

```text
runModel()
    ↓
adminAiService.runModel()
    ↓
mockAdminAiService.runModel()
    ↓
Mock 데이터 생성
    ↓
return result
    ↑
adminAiService
    ↑
runModel()
    ↓
state 갱신
```

즉 다른 파일을 호출해도 **결과가 호출한 함수로 다시 반환되는 과정**을 명확히 설명한다.

---

# 24. 파일을 따라가는 추천 순서

초심자가 직접 코드를 열어볼 때 어떤 순서로 보면 되는지 알려준다.

예:

```text
1. LlmPanel.tsx
   ↓

2. useLlmComparison.ts
   ↓

3. adminAiService.ts
   ↓

4. mockAdminAiService.ts
   ↓

5. llmMockData.ts
   ↓

6. 다시 useLlmComparison.ts
   ↓

7. LlmResultGrid.tsx / LlmResultCard.tsx
```

각 파일에서 어떤 함수부터 보면 되는지도 알려준다.

---

# 25. Frontend와 Backend 경계 설명

현재 Admin LLM 기능이 어디까지 Frontend인지 명확히 표시한다.

예:

```text
현재

Browser
→ React
→ Hook
→ Frontend Service
→ Mock Service
→ React
```

향후 실제 연결 구조가 예상되는 경우에는 별도 구분하여 설명한다.

```text
향후 예상

Browser
→ React
→ Hook
→ API Service
→ HTTP
→ FastAPI
→ LLM Service
→ 실제 LLM
```

향후 예상 구조와 현재 구현을 섞어 설명하지 않는다.

---

# 26. 전체 모델과 개별 모델의 상태 독립성 확인

다음 상황도 코드 기준으로 확인한다.

```text
전체 모델 실행 중 하나만 취소 가능한가?

모델 하나가 error여도 다른 모델은 success 가능한가?

단일 모델을 다시 실행했을 때 다른 모델 결과가 유지되는가?

전체 실행 중 각 결과가 완료되는 즉시 표시되는가?
```

현재 구현대로 설명한다.

---

# 27. 모델 정의 위치 확인

비교 대상 모델이 어디에 정의되어 있는지도 확인한다.

예:

```text
constants
modelOptions
mock fixture
types
```

다음 내용을 설명한다.

```text
모델 ID
화면 표시 이름
학습 상태 label
Mock 응답
```

이 각각 어느 파일에서 관리되는가?

같은 모델 정보가 여러 파일에 중복되어 있다면 그 사실만 알려준다.

이번 분석 작업에서 리팩터링하지 않는다.

---

# 28. 결과 출력 UI 분석

모델 실행 결과가 실제 어떤 Component에서 표시되는지 설명한다.

다음 데이터 각각을 어디서 출력하는지 확인한다.

```text
모델명
학습 상태
실행 상태
답변
응답 시간
Token 수
오류
취소 상태
```

---

# 29. 코드 전체 복사 금지

설명을 위해 전체 파일을 복사하지 않는다.

핵심 함수만 필요한 만큼 발췌한다.

예:

```ts
const runModel = async (modelId: string) => {
   ...
}
```

그리고 아래에서 각 단계의 의미를 설명한다.

---

# 30. 한국어로 쉽게 설명

대상 독자는 React/TypeScript와 비동기 흐름에 익숙하지 않은 초심자라고 가정한다.

다음 용어가 나오면 간단히 설명한다.

```text
Hook
State
Props
Callback
Promise
async / await
Service
Interface
Mock
AbortController
Controller
Re-render
```

단, JavaScript 기초 전체 강의를 하지는 않는다.

현재 코드 이해에 필요한 정도만 설명한다.

---

# 31. 설명할 때 비유 가능

필요하면 다음처럼 이해하기 쉽게 비유할 수 있다.

예:

```text
LlmPanel
→ 화면과 부품을 조립하는 곳

useLlmComparison
→ 전체 실행을 지휘하는 관리자

AdminAiService
→ LLM 기능을 요청하기 위한 공통 창구

mockAdminAiService
→ 실제 LLM 대신 테스트 응답을 만드는 대역

LlmResultCard
→ 돌아온 결과를 사용자에게 보여주는 화면
```

하지만 비유 다음에는 반드시 실제 기술적 역할을 설명한다.

---

# 32. 현재 코드의 중심 흐름을 마지막에 다시 요약

설명 마지막에는 가장 핵심적인 흐름을 짧게 다시 보여준다.

예:

```text
전체 실행 버튼
→ runAllModels()
→ 각 runModel()
→ AdminAiService
→ Mock Service
→ Result 반환
→ runModel()
→ State 변경
→ ResultCard 렌더링
```

그리고:

```text
현재는 여기까지가 Frontend 내부 Mock 동작이며,
FastAPI나 실제 LLM 호출은 아직 발생하지 않는다.
```

처럼 현재 연결 상태를 명확히 설명한다.

단, 실제 코드 확인 결과 API가 연결되어 있다면 그에 맞게 수정한다.

---

# 33. 결과물 형식

별도 코드 수정 없이 분석 결과만 출력한다.

설명은 다음 순서로 정리한다.

```text
1. 한눈에 보는 전체 구조

2. 가장 먼저 봐야 할 중심 파일

3. 전체 모델 실행 흐름

4. 단일 모델 실행 흐름

5. 실행 취소 흐름

6. 파일별 역할

7. State / Props / Callback 흐름

8. Service와 Mock 구조

9. Request / Result 데이터 구조

10. 결과가 화면에 표시되는 과정

11. 현재 Frontend와 Backend 연결 상태

12. 초심자용 코드 읽기 순서

13. 최종 한 줄 흐름 요약
```

---

# 중요 작업 원칙

이번 작업은 **분석 및 설명만 수행한다.**

다음을 절대 하지 않는다.

```text
코드 수정
리팩터링
파일 이동
새 파일 생성
Mock 변경
API 연결
Backend 변경
UI 변경
```

현재 코드가 이상하거나 개선할 부분이 발견되어도 먼저 수정하지 않는다.

필요하면 설명 마지막에:

```text
확인된 참고사항
```

정도로만 별도 표시한다.

---

# 최종 목표

설명을 읽은 초심자가 최소한 다음 흐름을 직접 코드에서 따라갈 수 있어야 한다.

```text
버튼 클릭
→ 어느 Component?
→ 어느 Hook?
→ 어느 중심 함수?
→ 어느 Service?
→ 어느 Mock 또는 API?
→ 결과가 어디로 return?
→ 어느 State가 변경?
→ 어느 Component가 다시 렌더링?
```

특히 **다른 파일의 함수를 호출한 뒤 결과가 다시 중심 실행 함수로 돌아오고, 그 결과로 React State가 갱신되어 화면이 바뀌는 과정​**을 가장 이해하기 쉽게 설명한다.