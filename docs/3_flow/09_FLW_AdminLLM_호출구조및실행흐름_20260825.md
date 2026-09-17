# Admin LLM 호출 코드 구조 및 실행 흐름 분석

> 분석 기준일: 2026-08-25  
> 분석 대상: 현재 작업 트리의 `/admin` LLM 탭 Frontend와 연결된 FastAPI·LLM Provider 코드  
> 작업 범위: 코드 변경 없이 현재 구현의 호출 순서, 데이터 이동, 상태 변경, 취소 동작 분석

## 1. 한눈에 보는 전체 구조

### 1.1 전체 모델 비교의 실제 한 줄 흐름

```text
LlmTestForm의 "전체 모델 비교 시작" 클릭
→ LlmPanel의 onRunAll
→ useLlmComparison.runAllModels()
→ 실행 가능한 모델마다 runModel()
→ executeModel()
→ adminAiService.runLlmModel()
→ apiAdminAiService.runLlmModel()
→ apiClient()의 fetch: POST /api/admin/llm/run
→ FastAPI run_llm()
→ admin_llm.run_model()
→ LlmApplicationService.run()
→ ModelRegistry로 모델 정의 확인
→ ProviderRegistry로 Ollama·Gemini·Mock Provider 선택
→ 선택된 Provider.generate()
→ 결과가 호출 경로의 역순으로 Frontend executeModel()까지 반환
→ setModelRuns()로 해당 모델 State 갱신
→ LlmResultGrid와 LlmResultCard 재렌더링
```

현재 전체 비교는 Backend의 `POST /api/admin/llm/compare`를 사용하지 않는다. Frontend의 `runAllModels()`가 실행 가능한 각 모델에 `runModel()`을 적용하고, 모델별 `POST /api/admin/llm/run` 요청을 동시에 보내는 구조다.

### 1.2 단일 모델 실행의 실제 한 줄 흐름

```text
LlmResultCard의 "모델 실행/다시 실행" 클릭
→ Card의 onRun
→ LlmResultGrid의 onRunModel(model.id)
→ LlmPanel의 llm.runModel(modelId)
→ useLlmComparison.runModel()
→ executeModel()
→ 이후 Service·HTTP·FastAPI·Provider 경로는 전체 실행과 동일
→ 해당 modelId의 State만 갱신
→ 해당 카드가 새 상태와 결과로 재렌더링
```

### 1.3 Frontend와 Backend 경계

```text
[Browser / Frontend]
React Component
→ useLlmComparison Hook
→ AdminAiService 계약
→ apiAdminAiService
→ apiClient(fetch)

========== HTTP 경계 ==========

[FastAPI / Backend]
/api/admin/llm/run Router
→ Admin LLM Facade
→ LlmApplicationService
→ ModelRegistry + ProviderRegistry
→ Ollama | Gemini | Mock Provider
```

따라서 현재 기능은 Frontend 내부 Mock만으로 끝나지 않는다. Browser에서 FastAPI로 실제 네트워크 요청이 발생한다. FastAPI 안에서 선택된 모델에 따라 로컬 Ollama, 외부 Gemini API, 또는 Backend Mock Provider가 실행된다.

## 2. 가장 먼저 봐야 할 중심 파일

가장 중요한 코드는 `frontend/src/features/admin/hooks/useLlmComparison.ts`다.

```text
중심 Hook       : useLlmComparison()
전체 실행 함수  : runAllModels()
단일 진입 함수  : runModel()
실제 1회 실행   : executeModel()
취소 함수       : cancelModel()
초기화 함수     : reset()
모델 목록 로딩  : loadModels()
```

`runModel()`은 모델과 Prompt를 검증하는 공개 진입점이고, `executeModel()`은 AbortController 생성, `running` 상태 전환, Service 호출, 성공·오류 상태 저장을 실제로 담당한다. 따라서 단일 실행의 전체 비동기 동작을 이해하려면 `runModel()`에서 `executeModel()`로 내려가는 부분을 함께 읽어야 한다.

Backend의 중심은 다음 세 파일이다.

```text
backend/app/services/admin_llm.py
→ HTTP Schema와 LLM Application 사이의 Facade

backend/app/services/llm/application.py
→ 모델에 맞는 Provider 선택과 실행 시간 측정

backend/app/services/llm/registry.py
→ modelId별 모델 정의와 providerKey 연결
```

## 3. 실행 전 모델 목록을 준비하는 흐름

LLM 실행 버튼을 누르기 전에 비교 대상과 실행 가능 여부가 먼저 준비된다.

`AdminPage`는 OCR과 LLM 패널을 모두 렌더링하고 `hidden` 속성으로 현재 탭만 보이게 한다. 따라서 `/admin`에 진입하면 초기 탭이 OCR이어도 `LlmPanel`과 `useLlmComparison`은 마운트되며 모델 목록 로딩을 시작한다.

```text
/admin 진입
→ AdminPage가 LlmPanel 마운트
→ useLlmComparison의 useEffect
→ loadModels()
→ adminAiService.listLlmModels(signal)
→ apiAdminAiService.listLlmModels()
→ GET /api/admin/llm/models
→ FastAPI get_llm_models()
→ admin_llm.list_models()
→ LlmApplicationService.list_models()
→ 모든 모델의 Provider 가용성을 병렬 확인
→ 모델 목록 반환
→ setModels(nextModels)
→ setModelRuns(createInitialModelRuns(nextModels))
```

`createInitialModelRuns()`는 각 모델을 다음과 같은 최초 상태로 만든다.

```ts
{ modelId: model.id, status: "idle" }
```

목록 로딩 중에는 `LlmResultGrid`가 “LLM Provider 상태를 확인하고 있습니다...”를 표시한다. 실패하면 `modelLoadError`와 “모델 목록 다시 불러오기” 버튼을 표시하고, 성공하면 `group` 값에 따라 `main`과 `other` 카드 영역을 만든다.

가용성 확인 방식은 Provider마다 다르다.

| Provider | 모델 목록 로딩 시 확인 내용 |
| --- | --- |
| Ollama | `GET {LLM_OLLAMA_BASE_URL}/api/tags`로 서버 연결과 설정 모델 설치 여부 확인 |
| Gemini | 활성화 설정, API Key 존재 여부, `google.genai` 패키지 설치 여부 확인. 이 단계에서는 Gemini 생성 API를 호출하지 않음 |
| Mock | `provider_model`에 해당하는 `MOCK_FIXTURES` 존재 여부 확인 |

## 4. 전체 모델 실행 흐름

### 4.1 버튼에서 Hook까지

1. 사용자가 `LlmTestForm`의 “전체 모델 비교 시작” 버튼을 클릭한다.
2. 버튼의 `onClick={props.onRunAll}`이 실행된다.
3. `LlmPanel`이 전달한 `onRunAll={() => void llm.runAllModels()}`가 호출된다.
4. `useLlmComparison.runAllModels()`가 전체 실행을 시작한다.

전체 실행 버튼은 다음 중 하나면 비활성화된다.

- 한 모델이라도 이미 `running`인 경우
- 전체 실행이 진행 중인 경우
- 모델 목록을 불러오는 중인 경우
- 실행 가능한 모델이 없는 경우

### 4.2 `runAllModels()`의 검증과 병렬 실행

`runAllModels()`는 다음 순서로 검사한다.

1. `allRunActiveRef.current` 또는 `hasRunningModels`가 참이면 중복 실행을 막고 종료한다.
2. `prompt.trim()`이 비어 있으면 공통 오류 State에 안내 문구를 저장한다.
3. `enabled && available`인 `runnableModels`가 없으면 오류를 저장한다.
4. 전체 실행 버전을 올리고 `allRunActiveRef.current = true`로 기록한다.
5. `setIsRunningAll(true)`로 전체 실행 UI를 활성화한다.
6. 다음 구조로 실행 가능한 모든 모델을 시작한다.

```ts
await Promise.allSettled(
  runnableModels.map((model) => runModel(model.id, runPrompt, file)),
);
```

관계는 다음과 같다.

```text
runAllModels()
   ├→ runModel("ollama-gemma3") → executeModel(...)
   ├→ runModel("gemini")        → executeModel(...)
   ├→ runModel("medgemma")      → executeModel(...)
   ├→ runModel("gemma")         → executeModel(...)
   ├→ runModel("qwen")          → executeModel(...)
   └→ runModel("llama")         → executeModel(...)
```

단, 실제 실행 대상은 `/llm/models` 응답에서 `enabled=true`이고 `available=true`인 모델만이다.

`Promise.allSettled()`는 모든 모델 실행이 끝날 때까지 전체 실행의 완료를 기다린다. 각 `executeModel()`은 자신의 오류를 해당 모델의 `error` State로 변환하므로 한 모델이 실패해도 다른 모델의 성공 결과는 유지된다.

### 4.3 모델별 결과가 도착하는 시점

전체 실행은 모든 결과를 모은 뒤 한 번에 표시하지 않는다. 각 `executeModel()`이 응답을 받는 즉시 해당 `modelId`의 `setModelRuns()`를 호출한다. 따라서 빠른 모델의 결과 카드가 먼저 `success`로 바뀌고, 느린 모델은 계속 `running`으로 남을 수 있다.

모든 원래 실행 Promise가 정리되면 전체 실행 버전이 여전히 유효한지 확인한 뒤 다음과 같이 종료한다.

```text
allRunActiveRef.current = false
setIsRunningAll(false)
```

## 5. 단일 모델 실행 흐름

### 5.1 카드에서 Hook까지

1. `LlmResultCard`의 “모델 실행” 또는 “다시 실행” 버튼을 클릭한다.
2. Card가 `onRun()` Callback을 호출한다.
3. `LlmResultGrid.ModelGroup`이 만든 `onRun={() => onRunModel(model.id)}`가 모델 ID를 올려 보낸다.
4. `LlmPanel`의 `onRunModel={(modelId) => void llm.runModel(modelId)}`가 실행된다.
5. `useLlmComparison.runModel(modelId)`가 현재 Hook의 `prompt`와 `file`을 기본값으로 사용한다.

### 5.2 `runModel()`과 `executeModel()`

`runModel()`은 다음을 확인한다.

- `models`에서 전달받은 `modelId`를 찾을 수 있는가?
- 모델이 `enabled`이고 `available`한가?
- 공백을 제거한 Prompt가 비어 있지 않은가?

검증에 성공하면 공통 오류를 지우고 `executeModel(modelId, runPrompt, sharedFile)`을 기다린다.

`executeModel()`의 실제 순서는 다음과 같다.

1. 같은 모델에 남아 있는 기존 Controller가 있으면 `abort()`한다.
2. 해당 모델의 `requestVersion`을 1 올린다.
3. 새 `AbortController`와 `startedAt`을 만든다.
4. Controller를 `controllersRef`의 `modelId` 위치에 저장한다.
5. `setModelRuns()`로 해당 모델만 `running` 상태로 교체한다.
6. `adminAiService.runLlmModel()`을 `await`한다.
7. 현재 요청 버전과 시작 당시 버전이 같은지 확인한다.
8. 정상 결과면 해당 모델만 `success`와 결과 값으로 교체한다.
9. 오류면 해당 모델만 `cancelled` 또는 `error`로 교체한다.
10. 아직 같은 요청이 최신 요청이면 Controller를 Map에서 제거한다.

상태 갱신은 기존 Map을 펼친 뒤 한 모델만 덮어쓴다.

```ts
setModelRuns((current) => ({
  ...current,
  [modelId]: { /* 새 실행 상태 또는 결과 */ },
}));
```

이 때문에 한 모델을 단독 재실행해도 다른 모델의 기존 결과는 유지된다.

## 6. 함수 호출 후 결과가 돌아오는 경로

다른 파일의 함수를 호출한 뒤 결과가 사라지는 것이 아니라, `await`한 호출자에게 역순으로 반환된다.

```text
Frontend executeModel()
    ↓ await
adminAiService.runLlmModel()
    ↓ 구현체 위임
apiAdminAiService.runLlmModel()
    ↓
apiClient<LlmModelResult>()
    ↓ fetch
POST /api/admin/llm/run
    ↓
FastAPI run_llm()
    ↓ await
admin_llm.run_model()
    ↓ await
LlmApplicationService.run()
    ↓ await
선택된 Provider.generate()
    ↓
ProviderGenerateResult 생성
    ↑
LlmApplicationService가 LlmExecutionResult로 감쌈
    ↑
admin_llm._to_run_response()가 LlmRunResponse로 변환
    ↑
FastAPI가 camelCase JSON 응답 생성
    ↑ HTTP response
apiClient가 response.json() 반환
    ↑
apiAdminAiService 반환
    ↑
adminAiService 계약을 통해 executeModel의 result에 도착
    ↓
setModelRuns()로 React State 갱신
```

HTTP 오류이면 FastAPI Router가 `LlmServiceError.status_code`와 안전한 메시지를 `detail`로 반환한다. `apiClient()`는 성공하지 않은 응답의 `detail`을 읽어 JavaScript `Error`를 던지고, `executeModel()`의 `catch`가 해당 카드의 `error` State로 저장한다.

## 7. 실행 취소 흐름

### 7.1 취소 버튼의 호출 경로

`LlmResultCard`는 해당 카드가 `running`일 때 실행 버튼 대신 “실행 취소” 버튼을 보여 준다.

```text
LlmResultCard의 실행 취소 클릭
→ onCancel()
→ LlmResultGrid의 onCancelModel(model.id)
→ LlmPanel의 llm.cancelModel(modelId)
→ useLlmComparison.cancelModel(modelId)
```

### 7.2 실제 취소 방법

`cancelModel()`은 `clearTimeout` 방식이 아니라 모델별 `AbortController`와 요청 버전 방식을 함께 사용한다.

1. `controllersRef`에서 해당 `modelId`의 Controller를 찾는다.
2. `requestVersionsRef`의 버전을 올려 현재 요청을 구버전으로 만든다.
3. `controller.abort()`로 Browser의 `fetch`에 전달된 `AbortSignal`을 중단한다.
4. Controller Map에서 해당 모델을 제거한다.
5. 해당 모델이 여전히 `running`이면 직접 `cancelled` State로 바꾼다.
6. `startedAt`부터 취소 시점까지의 Frontend 경과 시간을 저장한다.

`executeModel()`에는 Service 응답 직후와 오류 처리 직전에 다음 의미의 검사가 있다.

```text
현재 requestVersion !== 이 실행이 시작할 때의 requestVersion
→ 이미 취소·초기화·새 실행된 오래된 요청
→ 늦은 결과로 State를 덮어쓰지 않고 return
```

즉, Abort가 늦게 적용되거나 결과가 뒤늦게 도착해도 취소된 카드가 다시 `success` 또는 `error`로 바뀌는 것을 버전 검사로 막는다.

### 7.3 취소 범위와 한계

- Controller는 `modelId`별로 분리되어 있으므로 한 모델 취소가 다른 모델 요청을 취소하지 않는다.
- 전체 실행 중 한 모델만 취소할 수 있으며 나머지 모델은 계속 실행된다.
- `runAllModels()`는 나머지 모든 실행이 끝날 때까지 전체 실행 상태를 유지한다.
- Browser의 HTTP 요청 대기는 취소되지만, Provider 자체에 별도의 취소 API를 전달하지는 않는다.
- 따라서 FastAPI가 이미 Ollama·Gemini 추론을 시작했다면 서버 또는 Provider의 추론은 계속될 수 있다. UI의 취소 메시지도 이 한계를 명시한다.
- Component가 언마운트되거나 `reset()`이 실행될 때는 모든 Controller를 중단하고 모든 요청 버전을 무효화한다.

## 8. 파일별 역할

| 순서 | 파일 | 주요 함수/컴포넌트 | 역할 |
| ---: | --- | --- | --- |
| 1 | `frontend/src/app/router.tsx` | `router` | `/admin` URL에서 `AdminPage`를 렌더링 |
| 2 | `frontend/src/features/admin/pages/AdminPage.tsx` | `AdminPage` | OCR/LLM 탭 상태 관리와 `LlmPanel` 배치 |
| 3 | `frontend/src/features/admin/components/llm/LlmPanel.tsx` | `LlmPanel` | Hook 결과를 Form과 Grid에 연결하는 조립 지점 |
| 4 | `frontend/src/features/admin/components/llm/LlmTestForm.tsx` | `LlmTestForm` | Prompt·참고 파일 입력, 전체 실행·초기화 버튼 |
| 5 | `frontend/src/features/admin/hooks/useLlmComparison.ts` | `loadModels`, `runAllModels`, `runModel`, `executeModel`, `cancelModel`, `reset` | 모델 목록, 입력, 모델별 실행 상태와 비동기 흐름의 중심 |
| 6 | `frontend/src/features/admin/services/adminAiService.ts` | `AdminAiService`, `adminAiService` | UI/Hook이 의존하는 공통 Service 계약과 현재 구현체 선택 |
| 7 | `frontend/src/features/admin/services/apiAdminAiService.ts` | `listLlmModels`, `runLlmModel` | Frontend 데이터를 HTTP 요청으로 변환 |
| 8 | `frontend/src/services/apiClient.ts` | `apiClient` | Base URL 결합, `fetch`, JSON·HTTP 오류 처리 |
| 9 | `backend/app/api/admin/router.py` | `get_llm_models`, `run_llm` | FastAPI 요청 수신, Schema 검증, Service 오류의 HTTP 변환 |
| 10 | `backend/app/services/admin_llm.py` | `list_models`, `run_model`, `_to_run_response` | API Schema와 LLM Application 결과 사이의 Facade·변환 |
| 11 | `backend/app/services/llm/application.py` | `LlmApplicationService.list_models`, `run` | 가용성 확인, 모델·Provider 선택, 실행 시간 측정 |
| 12 | `backend/app/services/llm/registry.py` | `ModelRegistry`, `ProviderRegistry`, `create_model_registry` | 모델 ID, 표시 정보, Provider 연결의 기준 |
| 13 | `backend/app/services/llm/providers/ollama.py` | `OllamaLlmProvider` | 로컬 Ollama `/api/tags`, `/api/chat` 연동 |
| 14 | `backend/app/services/llm/providers/gemini.py` | `GeminiLlmProvider` | Google GenAI SDK로 Gemini 실제 응답 생성 |
| 15 | `backend/app/services/llm/providers/mock.py` | `MockLlmProvider`, `MOCK_FIXTURES` | 네 Mock 모델의 지연·답변·토큰·오류 생성 |
| 16 | `frontend/src/features/admin/components/llm/LlmResultGrid.tsx` | `LlmResultGrid`, `ModelGroup` | 모델 그룹 분리, 모델별 State와 Callback을 Card로 전달 |
| 17 | `frontend/src/features/admin/components/llm/LlmResultCard.tsx` | `LlmResultCard` | 모델 정보, 상태, 답변, 시간, 토큰, 오류와 실행·취소 UI 출력 |

## 9. State / Props / Callback 흐름

### 9.1 중심 Hook의 State

| State | Setter | 의미 |
| --- | --- | --- |
| `models` | `setModels` | Backend가 반환한 모델 정의와 가용성 목록 |
| `isLoadingModels` | `setIsLoadingModels` | 모델 목록 로딩 여부 |
| `modelLoadError` | `setModelLoadError` | 모델 목록 API 실패 메시지 |
| `prompt` | `setPrompt` | 사용자가 입력한 공통 질문 |
| `file` | `setFile` | 사용자가 고른 참고 파일 객체. 현재 전송에는 파일명만 사용 |
| `modelRuns` | `setModelRuns` | `modelId`별 실행 상태·답변·지표 Map |
| `isRunningAll` | `setIsRunningAll` | 전체 실행 Promise 묶음이 진행 중인지 표시 |
| `error` | `setError` | Prompt 누락, 실행 불가 등 Form 공통 오류 |

렌더링용 State 외에 다음 Ref가 비동기 제어 정보를 보관한다. Ref 값 변경 자체는 재렌더링을 만들지 않는다.

| Ref | 역할 |
| --- | --- |
| `controllersRef` | 모델별 `AbortController` 저장 |
| `requestVersionsRef` | 취소·재실행 뒤 오래된 결과 무시 |
| `allRunVersionRef` | 초기화·언마운트 뒤 오래된 전체 실행 종료 처리 무시 |
| `allRunActiveRef` | 전체 실행의 즉시 중복 진입 방지 |
| `modelListControllerRef` | 모델 목록 재조회·언마운트 시 이전 목록 요청 취소 |

`runnableModels`와 `hasRunningModels`는 기존 State에서 계산하는 `useMemo` 값이다.

`LlmResultCard`에는 카드 내부에서만 쓰는 `copied`와 `runningSeconds` State도 있다. `runningSeconds`는 `setInterval`로 0.1초마다 화면의 실행 경과 시간을 갱신하며 Provider의 최종 응답 시간과는 별개다.

### 9.2 데이터는 아래로, 이벤트는 위로

```text
상태 데이터 ↓

useLlmComparison
→ LlmPanel
→ LlmTestForm: prompt, file, 실행·로딩 여부, 공통 error
→ LlmResultGrid: models, modelRuns, 목록 로딩·오류
→ LlmResultCard: model, run

사용자 이벤트 ↑

LlmTestForm
→ onPromptChange / onFileChange / onRunAll / onReset
→ LlmPanel
→ useLlmComparison의 setter 또는 함수

LlmResultCard
→ onRun / onCancel
→ LlmResultGrid가 model.id 결합
→ LlmPanel
→ useLlmComparison.runModel / cancelModel
```

Props는 부모가 자식에게 전달하는 값이고, Callback은 자식의 사용자 이벤트를 부모 로직으로 알려 주는 함수다. 현재 구조는 Hook의 데이터가 아래쪽 Card로 내려가고, Card의 클릭 이벤트는 Callback을 통해 Hook으로 올라오는 전형적인 React 단방향 흐름이다.

## 10. Service와 실제·Mock Provider 구조

### 10.1 Component가 HTTP나 Mock을 직접 호출하지 않는 이유

`AdminAiService` Interface는 다음 두 LLM 계약을 제공한다.

```text
listLlmModels(signal?) → Promise<LlmModelDefinition[]>
runLlmModel(request)   → Promise<LlmModelResult>
```

Hook은 이 계약만 호출하고 URL, HTTP method, JSON 직렬화 방법을 알지 않는다. 현재 변수 연결은 다음과 같다.

```ts
export const adminAiService: AdminAiService = apiAdminAiService;
```

따라서 현재 구현은 다음 구조다.

```text
Hook
→ AdminAiService 계약
→ apiAdminAiService 구현체
→ FastAPI
```

이 중간 계약 덕분에 UI와 Hook을 그대로 둔 채 다른 구현체로 교체할 수 있는 경계가 생긴다. 다만 현재 저장소에는 Frontend용 `mockAdminAiService.ts` 또는 `llmMockData.ts`가 존재하지 않으며, `adminAiService`가 Mock 구현체를 선택하지도 않는다. Mock은 FastAPI 이후 Backend Provider 계층에 있다.

### 10.2 Backend의 Provider 선택

`create_model_registry()`는 `modelId`를 `provider_key`와 `provider_model`에 연결한다. `LlmApplicationService.run()`은 이 정의를 조회한 뒤 `ProviderRegistry`에서 Provider 객체를 선택한다.

```text
modelId
→ ModelRegistry.resolve(modelId)
→ LlmModelDefinition.provider_key
→ ProviderRegistry.resolve(provider_key)
→ provider.generate(request, definition)
```

### 10.3 현재 실제 모델과 Mock 모델

| 모델 ID | 화면 이름 | 그룹 | Provider | Provider 모델/Fixture Key | 형태 |
| --- | --- | --- | --- | --- | --- |
| `ollama-gemma3` | Gemma 3 (Local) | `main` | `ollama` | 설정의 `llm_ollama_model` | 실제 로컬 HTTP 호출 |
| `gemini` | Gemini 3.5 Flash-Lite | `main` | `gemini` | 설정의 `llm_gemini_model` | 실제 외부 SDK 호출 |
| `medgemma` | MedGemma | `other` | `mock` | `medgemma` | Backend Mock |
| `gemma` | Gemma (Mock) | `other` | `mock` | `gemma` | Backend Mock |
| `qwen` | Qwen | `other` | `mock` | `qwen` | Backend Mock |
| `llama` | Llama | `other` | `mock` | `llama` | 의도적으로 실패하는 Backend Mock |

모델 ID, 표시 이름, 학습 상태, 설명, 그룹, Provider 연결은 `backend/app/services/llm/registry.py`에서 관리한다. Frontend `constants/adminOptions.ts`에는 LLM 모델 목록이 없고 OCR 옵션만 있다. Mock 답변·지연·출력 Token·실패 여부는 `backend/app/services/llm/providers/mock.py`의 `MOCK_FIXTURES`에 따로 있다. 따라서 Mock 모델의 `provider_model` 문자열과 Fixture Key가 일치해야 한다.

### 10.4 Mock 결과 생성 방법

`MockLlmProvider.generate()`는 다음 방식으로 결과를 만든다.

- 지연: `await asyncio.sleep(fixture.delay_seconds)`
- 답변: Fixture의 고정 `answer`에 참고 문서 유무 안내 문구 추가
- 입력 Token: `max(64, round(trimmed prompt 길이 × 1.7) + 파일명이 있으면 18)`
- 출력 Token: Fixture의 고정 `output_tokens`
- 총 Token: 입력 Token + 출력 Token
- 종료 사유: `"mock"`
- 오류 Fixture: `llama`는 2.65초 후 `LlmProviderUnavailableError` 발생

지연 시간은 MedGemma 1.6초, Gemma Mock 2.35초, Qwen 1.85초, Llama 2.65초다. Frontend Mock의 `setTimeout`은 없으며, Backend의 `asyncio.sleep()`이 지연을 만든다. Card의 `setInterval`과 복사 안내용 `setTimeout`은 UI 시간 표시에만 사용된다.

### 10.5 실제 Provider 동작

```text
Ollama 실행
→ httpx POST {LLM_OLLAMA_BASE_URL}/api/chat
→ stream=false
→ message.content와 prompt_eval_count/eval_count 변환

Gemini 실행
→ google.genai 비동기 client
→ models.generate_content(model=..., contents=prompt)
→ response.text와 usage_metadata 변환
```

`LlmApplicationService`는 `provider.generate()` 호출 전후를 `time.perf_counter()`로 측정해 성공 응답의 `responseTimeSeconds`를 만든다.

## 11. Request / Result 데이터 구조

### 11.1 Frontend TypeScript 타입의 이동

| 타입 | 생성·관리 위치 | 전달·사용 위치 |
| --- | --- | --- |
| `LlmModelDefinition` | `GET /llm/models` 응답으로 생성 | Hook의 `models` → Panel/Grid/Card. 표시 정보와 실행 가능 여부 판단 |
| `RunLlmModelRequest` | `executeModel()`이 Prompt, modelId, File, signal로 생성 | `AdminAiService` → `apiAdminAiService`. File 전체 대신 `file.name`만 JSON으로 변환 |
| `LlmModelResult` | `POST /llm/run` JSON 응답 | `executeModel()`이 받아 `LlmModelRun` State로 복사 |
| `LlmRunStatus` | Hook이 실행 단계에 따라 지정 | Card의 상태 Badge, 본문, 실행/취소 버튼 분기 |
| `LlmModelRun` | `createInitialModelRuns()`와 `executeModel()`에서 생성·교체 | 한 모델의 현재 상태, 답변, 오류, 지표 보관 |
| `LlmModelRunMap` | Hook의 `modelRuns` State | `Record<modelId, LlmModelRun>` 형태로 모든 카드 상태 보관 |

### 11.2 실제 실행 요청 데이터

Hook에서 Service로 전달되는 값:

```text
prompt: string
modelId: string
file?: File
signal?: AbortSignal
```

`apiAdminAiService`가 HTTP JSON으로 바꾸는 값:

```json
{
  "prompt": "사용자 질문",
  "modelId": "gemini",
  "documentName": "선택한 파일명 또는 null"
}
```

선택한 파일의 본문이나 바이너리는 업로드되지 않는다. Backend Provider에는 `prompt`와 `document_name`만 전달된다. 실제 Ollama와 Gemini Provider는 현재 생성 요청에서 `document_name`을 사용하지 않으며, Mock Provider만 파일명 안내 문구와 입력 Token 계산에 반영한다.

### 11.3 실제 성공 결과 데이터

FastAPI는 Backend snake_case 필드를 Frontend용 camelCase JSON으로 반환한다.

```text
modelId
provider
providerModel
answer
responseTimeSeconds
inputTokens
outputTokens
totalTokens
finishReason
isMock
```

`executeModel()`은 이 값을 해당 `modelId`의 `LlmModelRun`에 저장한다. Token을 Provider가 제공하지 않으면 `null`일 수 있고 Card에는 “계산 안 됨”으로 표시된다.

### 11.4 Backend 내부 계약

```text
HTTP LlmRunRequest
→ ProviderGenerateRequest(prompt, document_name)
→ ProviderGenerateResult(answer, tokens, finish_reason)
→ LlmExecutionResult(definition, provider, is_mock, result, elapsed)
→ HTTP LlmRunResponse
```

`backend/app/schemas/admin.py`는 HTTP 요청·응답 검증과 camelCase Alias를 담당하고, `backend/app/services/llm/contracts.py`의 Dataclass와 Protocol은 Application과 Provider가 공유하는 내부 계약을 담당한다.

## 12. 모델 실행 상태와 독립성

현재 존재하는 상태는 `idle`, `running`, `success`, `error`, `cancelled` 다섯 가지다.

```text
모델 목록 로드 또는 초기화
→ idle

executeModel() 시작
→ running

Service 정상 반환
→ success

Service/HTTP/Provider 오류
→ error

사용자 취소 또는 AbortError
→ cancelled
```

| 확인 항목 | 현재 동작 |
| --- | --- |
| 전체 실행 중 하나만 취소 | 가능. 해당 `modelId`의 Controller와 State만 변경 |
| 한 모델 오류 시 다른 모델 성공 | 가능. 모델별 State이며 전체는 `allSettled` 사용 |
| 단일 모델 재실행 시 다른 결과 유지 | 유지. State Map에서 해당 Key만 덮어씀 |
| 전체 실행 결과 표시 시점 | 각 모델 완료 즉시 표시. 전체 완료까지 기다려 일괄 표시하지 않음 |
| 한 모델 실행 중 다른 모델 단일 실행 | Card별 실행 버튼이므로 실행 가능한 다른 모델은 시작 가능 |
| 한 모델 실행 중 전체 실행 시작 | 불가능. `hasRunningModels`로 전체 버튼과 함수 진입 차단 |

전체 실행은 단일 실행과 완전히 다른 구현이 아니다. “실행 가능한 모든 모델에 단일 실행 함수 `runModel()`을 적용하고 모두 정리될 때까지 기다리는 관리자 함수”다.

## 13. 결과가 화면에 표시되는 과정

Service나 Mock Provider가 DOM을 직접 변경하지 않는다.

```text
Provider 결과 반환
→ executeModel()의 result 변수
→ setModelRuns(current => 새 Map)
→ React가 modelRuns 변경 감지
→ LlmPanel 재렌더링
→ LlmResultGrid가 새 run을 Card에 전달
→ LlmResultCard가 status와 결과에 맞춰 출력
```

`LlmResultCard`의 출력 위치는 다음과 같다.

| 출력 데이터 | 실제 출처와 표시 방식 |
| --- | --- |
| 모델명 | `model.label`을 `<h4>`에 표시 |
| 모델 계열·Provider/Mock | `model.family`, `model.isMock`, `model.provider` Badge |
| 학습 상태·설명 | `model.trainingStage`, `model.description` |
| 실행 상태 | `run.status`를 `STATUS_LABELS`와 Icon으로 표시 |
| 답변 | `success`일 때 `run.answer` 표시 및 Clipboard 복사 제공 |
| 응답 시간 | 실행 중에는 Card의 경과 시간, 완료 후 `run.responseTimeSeconds` |
| Token 수 | `run.inputTokens`, `outputTokens`, `totalTokens`; 없으면 “계산 안 됨” |
| 오류 | `error`일 때 `run.error`를 Alert로 표시 |
| 취소 | `cancelled`일 때 `run.error`의 취소 안내 표시 |

결과의 `provider`, `providerModel`, `isMock`, `finishReason`도 Hook State에 저장되지만 현재 Card 본문은 이 실행 결과 필드를 직접 출력하지 않는다. Provider Badge는 모델 목록의 `model.provider`와 `model.isMock`을 사용한다.

## 14. 현재 네트워크 호출 여부와 API 경계

Frontend `apiClient()`는 다음 Base URL을 사용한다.

```text
VITE_API_URL이 있으면 해당 값
없으면 http://localhost:8000/api
```

현재 Admin LLM 흐름에서 확인되는 네트워크 요청은 다음과 같다.

| 시점 | 요청 | 목적 |
| --- | --- | --- |
| `/admin` 마운트·목록 재조회 | `GET /api/admin/llm/models` | 모델 정의와 현재 가용성 조회 |
| 모델 한 번 실행 | `POST /api/admin/llm/run` | 한 모델 실행 |
| 전체 비교 | 실행 가능 모델 수만큼 `POST /api/admin/llm/run` | 모델별 독립 실행 |
| Ollama 가용성 확인 | Backend → Ollama `GET /api/tags` | 설치 모델 확인 |
| Ollama 실행 | Backend → Ollama `POST /api/chat` | 실제 로컬 모델 생성 |
| Gemini 실행 | Backend Google GenAI SDK → Gemini API | 실제 외부 모델 생성 |

FastAPI 전체 경로는 `settings.api_prefix`의 기본값 `/api`, Admin Router Prefix `/admin`, Endpoint `/llm/models` 또는 `/llm/run`이 합쳐져 만들어진다.

`POST /api/admin/llm/compare`도 Backend에 남아 있지만 현재 Admin LLM UI의 전체 비교에는 연결되어 있지 않다. 이 Endpoint와 현재 UI의 `runAllModels()` 흐름을 혼동하면 안 된다.

## 15. 초심자용 용어 정리

| 용어 | 이 코드에서의 뜻 |
| --- | --- |
| Hook | Component 밖에서 React State와 실행 로직을 묶은 함수. 여기서는 `useLlmComparison` |
| State | 값이 바뀌면 React가 화면을 다시 그리는 데이터. 예: `modelRuns` |
| Props | 부모 Component가 자식에게 내려주는 데이터와 함수 |
| Callback | 자식의 클릭·입력 이벤트를 부모 로직에 알리는 함수 |
| Promise | 지금은 결과가 없지만 비동기 작업 후 성공 값 또는 오류가 정해지는 객체 |
| `async` / `await` | 비동기 결과가 돌아올 때까지 함수 흐름을 읽기 쉽게 기다리는 문법 |
| Service | UI와 HTTP·Backend 세부 구현 사이의 호출 경계 |
| Interface | 구현체가 지켜야 하는 TypeScript 함수 형태의 계약 |
| Mock | 실제 모델 대신 정해진 지연·답변·오류를 만드는 대역. 현재는 Backend Provider |
| AbortController | `fetch` 요청에 취소 신호를 보내는 Browser API |
| Ref | 렌더링 없이 최신 Controller·요청 버전 같은 값을 보관하는 React 저장소 |
| Re-render | State 변경 후 React가 Component 출력 내용을 다시 계산하는 과정 |

비유하면 `LlmPanel`은 화면 부품을 연결하는 조립 지점, `useLlmComparison`은 전체 실행을 지휘하고 기록하는 관리자, `AdminAiService`는 공통 접수 창구, `LlmApplicationService`는 모델과 담당 Provider를 배정하는 Backend 관리자, `LlmResultCard`는 돌아온 결과를 보여 주는 전광판이다.

## 16. 초심자용 코드 읽기 순서

1. `frontend/src/features/admin/components/llm/LlmPanel.tsx`
   - `useLlmComparison()` 반환값이 Form과 Grid의 어느 Props로 전달되는지 본다.
2. `frontend/src/features/admin/components/llm/LlmTestForm.tsx`
   - 전체 실행 버튼의 `onClick={props.onRunAll}`을 찾는다.
3. `frontend/src/features/admin/hooks/useLlmComparison.ts`
   - `runAllModels()` → `runModel()` → `executeModel()` 순서로 읽는다.
4. `frontend/src/features/admin/services/adminAiService.ts`
   - Hook이 호출하는 계약과 현재 `apiAdminAiService` 연결을 확인한다.
5. `frontend/src/features/admin/services/apiAdminAiService.ts`
   - `runLlmModel()`이 만드는 URL, JSON Body, AbortSignal을 본다.
6. `frontend/src/services/apiClient.ts`
   - 실제 `fetch`와 오류 변환을 확인한다.
7. `backend/app/api/admin/router.py`
   - `run_llm()`이 요청을 받고 Service 오류를 HTTP 오류로 바꾸는 부분을 본다.
8. `backend/app/services/admin_llm.py`
   - `run_model()`과 `_to_run_response()`의 요청·응답 변환을 본다.
9. `backend/app/services/llm/application.py`
   - `run()`이 Model Registry와 Provider Registry를 사용하는 순서를 본다.
10. `backend/app/services/llm/registry.py`
    - `create_model_registry()`에서 모델 ID와 Provider 연결을 찾는다.
11. 선택된 Provider 파일
    - `providers/ollama.py`, `providers/gemini.py`, `providers/mock.py`의 `generate()`를 본다.
12. 다시 `useLlmComparison.ts`
    - `await` 아래의 `setModelRuns()`로 결과가 돌아오는 지점을 확인한다.
13. `LlmResultGrid.tsx` → `LlmResultCard.tsx`
    - 갱신된 State가 Props로 내려가 화면에 표시되는 과정을 본다.

단일 실행을 따라갈 때는 `LlmResultCard.tsx`의 실행 버튼에서 시작해 `LlmResultGrid`와 `LlmPanel`의 Callback을 역방향으로 올라간 뒤, 위 순서의 3번부터 이어서 읽으면 된다.

## 17. 확인된 참고사항

- 지시문에서 예상한 Frontend `mockAdminAiService`와 `llmMockData`는 현재 존재하지 않는다. Mock 응답은 Backend의 `MockLlmProvider`와 `MOCK_FIXTURES`가 만든다.
- 전체 비교는 Backend의 다중 비교 Endpoint가 아니라 Frontend의 복수 단일 실행 요청으로 구현되어 있다.
- 참고 파일은 `File`로 Hook에 보관되지만 HTTP 요청에는 `documentName`만 들어간다. 파일 내용, OCR Text, Chunk는 LLM에 전달되지 않는다.
- `AdminPage`는 비활성 탭을 제거하지 않고 숨기므로 LLM 모델 목록은 LLM 탭 클릭 시점이 아니라 `/admin` 화면 마운트 시점부터 로드된다.
- 실행 성공 시간은 Backend Provider 실행 시간이고, 오류·취소 시간은 Frontend에서 측정한 경과 시간이다.
- 취소는 Browser 요청과 늦은 UI 반영을 중단하지만 이미 시작된 Provider 추론의 종료를 보장하지 않는다.

## 18. 최종 핵심 요약

```text
[전체 실행]
전체 모델 비교 시작
→ LlmTestForm onRunAll
→ useLlmComparison.runAllModels()
→ 실행 가능 모델별 runModel()
→ executeModel()
→ AdminAiService / apiAdminAiService
→ 모델마다 POST /api/admin/llm/run
→ FastAPI run_llm()
→ admin_llm.run_model()
→ LlmApplicationService.run()
→ Registry가 Ollama·Gemini·Mock Provider 선택
→ Provider 결과 반환
→ executeModel()의 setModelRuns()
→ 모델별 LlmResultCard 즉시 재렌더링
```

```text
[단일 실행]
LlmResultCard 실행 버튼
→ Callback으로 modelId 전달
→ 같은 runModel()과 executeModel()
→ 같은 Service·HTTP·Backend·Provider 경로
→ 해당 modelId의 State만 갱신
→ 해당 카드 재렌더링
```

가장 중요한 결론은 다음과 같다. **전체 실행은 단일 실행 함수를 여러 모델에 병렬 적용하는 구조이고, 각 Provider의 결과는 호출 경로를 역순으로 `executeModel()`에 돌아온 뒤 `modelRuns` State를 바꾸며, React가 그 변경을 감지해 각 결과 카드를 다시 그린다.**
