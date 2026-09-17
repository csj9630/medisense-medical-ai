# LLM Ollama Gemma 3·Gemini 확장형 연동 구현 지시문

작성일: 2026-08-20  
대상: `thegpt-project`의 Admin LLM 비교 기능  
기준 브랜치/상태: `csj-ocr`, Backend Mock 기반 `/api/admin/llm/run` 구현 이후

## 1. 작업 목표

현재 Admin LLM 비교 화면의 Backend Mock 중 실제 모델 연결이 필요한 부분을 확장형 구조로 전환한다.

이번 구현의 1차 목표는 다음 두 모델을 Frontend → FastAPI Backend → LLM Provider 흐름으로 실제 호출하는 것이다.

1. 로컬 Ollama에 설치된 순정 `gemma3:1b`
2. Google AI Studio에서 발급한 무료 등급 API 키로 호출하는 Gemini `gemini-3.5-flash-lite`

단순히 두 모델을 조건문으로 연결하지 않는다. 이후 개발자가 다른 Ollama 모델, Gemini 모델, 별도 HTTP API 또는 새로운 LLM Provider를 추가할 때 기존 Router·Frontend 실행 로직을 반복 수정하지 않도록 Provider 인터페이스와 모델 레지스트리를 중심으로 설계한다.

## 2. 현재 구조와 유지할 계약

현재 단일 모델 실행 흐름은 다음과 같다.

```text
Frontend LlmResultCard
→ useLlmComparison.executeModel(modelId)
→ adminAiService.runLlmModel()
→ POST /api/admin/llm/run
→ app.services.admin_llm.run_model()
→ Backend Mock fixture
```

다음 동작은 유지한다.

- 모델별 개별 실행
- 전체 모델 병렬 실행
- 먼저 완료된 카드부터 결과 표시
- 모델별 성공·오류·취소 상태 분리
- 재실행된 이전 요청이 최신 상태를 덮어쓰지 않는 요청 버전 검증
- Frontend와 Backend 사이의 camelCase JSON 계약
- 기존 OCR 탭과 OCR 처리 코드

현재 `documentName`은 파일 내용이 아니라 파일명만 전달한다. 이번 작업에서 RAG, 파일 업로드, OCR 결과 주입, VectorDB 검색을 임의로 구현하지 않는다. 참고 문서 내용이 실제 모델로 전달되는 것처럼 표시하지도 않는다.

## 3. 이번 구현 범위

### 포함

- Ollama `gemma3:1b` 실제 비스트리밍 채팅 호출
- Gemini `gemini-3.5-flash-lite` 실제 비스트리밍 텍스트 호출
- 공통 LLM Provider Protocol 또는 추상 인터페이스
- Backend 중심 모델 레지스트리
- Frontend가 Backend 모델 목록을 조회하는 API
- Provider별 설정, 제한시간, 오류 변환, 실제 Token 사용량 처리
- API 키 비노출과 로그 마스킹
- 단위 테스트, API 계약 테스트, Provider 통합 테스트 절차
- README, `.env.example`, 구현 결과 보고서 갱신

### 제외

- Ollama 모델 자동 다운로드
- Ollama `Modelfile` 생성, 파인튜닝, LoRA 또는 양자화 변경
- Streaming/SSE/WebSocket
- 채팅 대화 이력 저장
- RAG 및 VectorDB 실제 연결
- Gemini Files API를 통한 문서 업로드
- 도구 호출, 함수 호출, 이미지·음성 입력
- 인증·권한 시스템 개편
- OCR 탭 재설계

## 4. 구현 원칙

### 4.1 Provider와 Model을 분리한다

`gemma3:1b`와 `gemini-3.5-flash-lite`를 Router의 `if/elif`로 직접 분기하지 않는다.

다음 개념을 분리한다.

- Provider: Ollama, Gemini, Mock, 향후 OpenAI 호환 API 등 호출 방식
- Model Definition: UI에서 사용하는 안정적인 Model ID와 실제 Provider 모델명 매핑
- Provider Result: Provider별 응답을 공통 형식으로 정규화한 결과
- Registry: Model ID로 Model Definition과 Provider를 조회하는 단일 진실 공급원

권장 흐름:

```text
POST /admin/llm/run
→ LlmApplicationService.run(model_id, prompt)
→ ModelRegistry.resolve(model_id)
→ ProviderRegistry.get(definition.provider)
→ provider.generate(request, definition)
→ ProviderResult
→ LlmRunResponse
```

### 4.2 Frontend는 Provider SDK를 직접 호출하지 않는다

- Ollama와 Gemini 호출은 반드시 Backend가 수행한다.
- `GEMINI_API_KEY`는 Frontend 환경변수, 번들, Network 요청 본문, 응답, 로그에 노출하지 않는다.
- Frontend는 기존 Backend API 주소만 호출한다.
- CORS를 열어 Frontend에서 Ollama `11434` 포트에 직접 접근하는 방식은 사용하지 않는다.

### 4.3 최종 모델 구성과 Model ID

기존 첫 번째 비교 영역의 다음 두 Mock 모델은 제거한다.

| 제거할 Model ID | 기존 표시 이름 | 기존 상태 |
| --- | --- | --- |
| `main-fine-tuned` | Main Model | 학습 + 파인튜닝 완료 Mock |
| `main-partial` | Comparison Model | 일부 데이터 학습 Mock |

두 자리를 실제 Ollama Gemma 3와 Gemini로 교체한다. 전체 여섯 모델의 최종 구성은 다음과 같다.

| 영역 | Frontend/API Model ID | 표시 이름 | Provider | 실제 Provider 모델명 | 실행 방식 |
| --- | --- | --- | --- | --- | --- |
| 첫 번째 비교 | `ollama-gemma3` | Gemma 3 (Local) | `ollama` | 설정값, 기본 `gemma3:1b` | 실제 호출 |
| 첫 번째 비교 | `gemini` | Gemini 3.5 Flash-Lite | `gemini` | 설정값, 기본 `gemini-3.5-flash-lite` | 실제 호출 |
| 다른 LLM 비교 | `medgemma` | MedGemma | `mock` | `medgemma` fixture | Mock |
| 다른 LLM 비교 | `gemma` | Gemma (Mock) | `mock` | `gemma` fixture | Mock |
| 다른 LLM 비교 | `qwen` | Qwen | `mock` | `qwen` fixture | Mock |
| 다른 LLM 비교 | `llama` | Llama | `mock` | `llama` fixture | Mock |

`main-fine-tuned`, `main-partial`의 고정 답변, 지연시간, Token fixture와 Frontend 상수는 제거한다. 사용 중인 외부 계약이 발견되지 않는 한 두 ID의 호환 alias를 만들지 않는다. 오래된 ID가 요청되면 다른 알 수 없는 Model ID와 동일하게 422를 반환한다.

실제 Ollama Gemma 3와 기존 `gemma` Mock은 서로 다른 모델이다. 혼동을 막기 위해 실제 모델은 `ollama-gemma3`, 기존 Mock은 `gemma` ID를 사용하며 UI Label과 Badge에서도 각각 `Local Ollama`, `Mock`을 명확히 표시한다.

실제 모델처럼 보이는 가짜 응답은 금지한다. `medgemma`, `gemma`, `qwen`, `llama`는 Mock Provider에 남기되 Registry와 API 응답에서 `isMock: true`가 자동으로 계산되어야 한다.

## 5. 권장 Backend 구조

현재 프로젝트 구조에 맞춰 다음과 같이 책임을 나눈다. 파일명은 기존 코드와 충돌 여부를 확인해 조정할 수 있지만 계층의 책임은 유지한다.

```text
backend/app/services/llm/
├─ __init__.py
├─ contracts.py          # Provider 요청/결과, 오류, Protocol
├─ registry.py           # Model Definition 및 Provider 매핑
├─ application.py        # run/list orchestration
└─ providers/
   ├─ __init__.py
   ├─ ollama.py          # Ollama REST 호출
   ├─ gemini.py          # google-genai 호출
   └─ mock.py            # 아직 실제 연결되지 않은 기존 모델
```

기존 `backend/app/services/admin_llm.py`는 다음 중 한 방식으로 정리한다.

- Admin Router가 새 application service를 사용하도록 얇은 호환 Facade로 유지
- 또는 책임을 새 모듈로 이동하고 import 경로와 테스트를 함께 갱신

Router에 Provider 세부 구현을 넣지 않는다.

## 6. 공통 Provider 계약

Provider 구현이 최소한 다음 계약을 만족하도록 한다.

```python
class LlmProvider(Protocol):
    async def generate(
        self,
        request: ProviderGenerateRequest,
        model: LlmModelDefinition,
    ) -> ProviderGenerateResult: ...

    async def check_availability(
        self,
        model: LlmModelDefinition,
    ) -> ProviderAvailability: ...
```

`ProviderGenerateRequest` 권장 필드:

- `prompt`
- 선택적 `system_prompt`
- `max_output_tokens`
- 추후 확장을 위한 생성 옵션 객체

`ProviderGenerateResult` 권장 필드:

- `answer`
- `provider`
- `provider_model`
- `input_tokens: int | None`
- `output_tokens: int | None`
- `total_tokens: int | None`
- `finish_reason: str | None`
- Provider가 반환한 request/response 식별자 중 비밀이 아닌 값

Token 수를 문자 길이 기반으로 임의 계산하지 않는다. Provider가 Token 사용량을 반환하면 그 값을 사용하고, 제공하지 않으면 `None`으로 유지해 UI에서 `계산 안 됨`으로 표시한다.

## 7. Model Registry

Model Registry는 최소한 다음 metadata를 관리한다.

- 안정적인 `id`
- `label`
- `provider_key`
- 실제 `provider_model`
- UI `group`
- 설명과 학습 단계 Label
- `enabled`
- 선택적 기본 생성 설정

`is_mock`을 각 모델에 수동으로 중복 저장하지 않는다. 선택된 Provider의 종류가 `mock`인지에 따라 Registry 또는 application service가 `isMock`을 계산한다. 이렇게 해야 Provider만 교체했는데 UI에는 계속 Mock으로 남는 설정 불일치를 막을 수 있다.

권장 Registry 표현 예시는 다음과 같다.

```python
LLM_MODELS = {
    "ollama-gemma3": LlmModelDefinition(
        provider_key="ollama",
        provider_model=settings.llm_ollama_model,
        group="main",
    ),
    "gemini": LlmModelDefinition(
        provider_key="gemini",
        provider_model=settings.llm_gemini_model,
        group="main",
    ),
    "medgemma": LlmModelDefinition(
        provider_key="mock",
        provider_model="medgemma",
        group="other",
    ),
}
```

나머지 `gemma`, `qwen`, `llama`도 같은 방식으로 `provider_key="mock"`에 등록한다.

### 7.1 Mock에서 실제 Provider로 교체하는 방법

Mock 모델을 실제 모델로 바꿀 때 Router, Schema, Frontend Hook 또는 카드 컴포넌트를 수정하지 않아야 한다.

예를 들어 향후 로컬에 실제 MedGemma를 설치했다면 Registry의 다음 값만 교체할 수 있어야 한다.

```python
# 변경 전
"medgemma": LlmModelDefinition(
    provider_key="mock",
    provider_model="medgemma",
    group="other",
)

# 변경 후
"medgemma": LlmModelDefinition(
    provider_key="ollama",
    provider_model="실제-ollama-model-tag",
    group="other",
)
```

같은 Provider의 실제 모델로 전환하는 경우 허용되는 필수 변경은 Registry 항목과 관련 환경설정뿐이다. 새로운 호출 방식이면 새 Provider 구현과 Provider Registry 등록이 추가될 수 있지만 공통 API와 Frontend 실행 계약은 유지한다.

Mock 답변·지연·오류 fixture는 `MockProvider` 내부에서 `provider_model`을 키로 조회한다. Model Registry나 application service에 Mock 생성 로직을 넣지 않는다.

새 모델 추가 시 이상적인 변경 범위는 다음과 같아야 한다.

1. 기존 Provider를 사용하면 Registry 항목 추가와 설정 추가
2. 새로운 Provider면 Provider 구현 1개와 Registry 등록
3. 공통 API Router와 Frontend 실행 Hook은 변경하지 않음

Registry는 알려지지 않은 Model ID를 422로 거부한다. Frontend가 보낸 Provider 이름이나 실제 upstream 모델명을 그대로 신뢰해 임의 호출하지 않는다. 이 규칙은 SSRF, 예상치 못한 과금, 허용하지 않은 모델 호출을 막기 위해 필요하다.

## 8. Ollama Gemma 3 구현

### 8.1 기본 설정

```dotenv
LLM_OLLAMA_ENABLED=true
LLM_OLLAMA_BASE_URL=http://127.0.0.1:11434
LLM_OLLAMA_MODEL=gemma3:1b
LLM_OLLAMA_TIMEOUT_SECONDS=120
LLM_OLLAMA_MAX_CONCURRENCY=1
```

최상위 `.env.example`에는 빈 비밀값과 안전한 예시만 추가한다. 실제 로컬 `.env` 값은 커밋하지 않는다.

### 8.2 사전 준비

개발자가 직접 다음을 수행하도록 README에 안내한다.

```powershell
ollama --version
ollama list
ollama pull gemma3
```

Backend가 모델을 자동으로 `pull`하지 않는다. 사용자가 말한 “순정 Gemma 3”는 `gemma3` 기본 모델을 그대로 호출한다는 뜻이며, 별도 `Modelfile`, 커스텀 가중치 또는 파인튜닝 모델을 만들지 않는다.

### 8.3 호출 방식

Backend에서 Ollama REST API를 비동기로 호출한다.

```text
POST {LLM_OLLAMA_BASE_URL}/api/chat
```

요청 핵심값:

```json
{
  "model": "gemma3",
  "messages": [
    {"role": "user", "content": "사용자 질문"}
  ],
  "stream": false
}
```

- `httpx.AsyncClient`를 Backend 직접 의존성으로 명시한다.
- 연결 제한시간과 전체 읽기 제한시간을 구분해 설정한다.
- 응답 `message.content`를 답변으로 사용한다.
- `prompt_eval_count`를 Input Token으로 사용한다.
- `eval_count`를 Output Token으로 사용한다.
- 두 값이 있으면 합계를 계산하고, 없으면 누락값을 위조하지 않는다.
- `done_reason`을 공통 `finish_reason`으로 정규화한다.
- 원본 전체 응답이나 사용자 Prompt를 운영 로그에 남기지 않는다.

### 8.4 가용성 확인

`GET {LLM_OLLAMA_BASE_URL}/api/tags`로 Ollama 연결과 `gemma3` 설치 여부를 구분한다.

- 서버 연결 실패: Provider unavailable
- 서버는 연결되지만 모델 없음: Model not installed
- 모델 존재: Available

## 9. Gemini 구현

### 9.1 SDK와 기본 설정

Google이 권장하는 현재 Python SDK인 `google-genai`를 사용한다. 유지보수 중단된 `google-generativeai`는 새로 추가하지 않는다.

```dotenv
LLM_GEMINI_ENABLED=true
GEMINI_API_KEY=
LLM_GEMINI_MODEL=gemini-3.5-flash-lite
LLM_GEMINI_TIMEOUT_SECONDS=60
LLM_GEMINI_MAX_CONCURRENCY=2
```

- API 키가 비어 있으면 Backend 시작 자체를 실패시키지 않는다.
- 대신 Gemini 모델을 `unavailable`로 내려 UI 실행 버튼을 비활성화한다.
- API 키 문자열을 오류 메시지, repr, 로그, 응답에 포함하지 않는다.
- `GOOGLE_API_KEY`와 `GEMINI_API_KEY`의 암묵적 우선순위에 기대지 말고 프로젝트 설정에서 사용할 키를 명확히 전달한다.

### 9.2 기본 모델 판단

2026-08-20 기준 실제 무료 API 키 호출 검증에 성공한 안정 모델 `gemini-3.5-flash-lite`를 기본값으로 사용한다.

단, 무료 등급의 실제 RPM/TPM/RPD, 지역·계정별 가용성, 모델 제공 여부는 바뀔 수 있다. 모델명을 코드 상수로 고정하지 않고 환경변수로 교체 가능하게 하며, 429 응답에는 AI Studio에서 현재 할당량을 확인하라는 메시지를 제공한다.

무료 등급 데이터는 Google 제품 개선에 사용될 수 있다고 공식 가격 문서에 표시되어 있다. 의료·개인정보·민감 문서를 Gemini 무료 API로 전송할 수 있다는 점을 UI 또는 운영 안내에 명확히 표시한다. 이번 범위에서는 선택 파일의 내용은 Gemini에 업로드하지 않는다.

### 9.3 호출 방식

FastAPI의 async 흐름을 막지 않도록 `client.aio.models.generate_content(...)`를 사용한다.

```python
response = await client.aio.models.generate_content(
    model=settings.llm_gemini_model,
    contents=prompt,
)
```

- 비스트리밍 텍스트 응답만 지원한다.
- `response.text`가 비어 있으면 성공으로 처리하지 말고 안전한 Provider 응답 오류로 변환한다.
- SDK `usage_metadata`의 Prompt/Candidate/Total Token을 공통 결과로 매핑한다.
- SDK client가 만든 네트워크 자원을 명시적으로 닫는다.
- Provider timeout을 적용한다.
- 안전 정책 차단, 429 quota, 인증 실패, upstream 5xx를 구분한다.
- 자동 재시도는 기본적으로 하지 않는다. 추후 재시도를 추가할 경우 429/5xx만 제한적으로 처리하고 사용자 실행을 중복 과금하지 않도록 한다.

## 10. API 계약

### 10.1 모델 목록

다음 Endpoint를 추가한다.

```text
GET /api/admin/llm/models
```

권장 응답:

```json
[
  {
    "id": "ollama-gemma3",
    "label": "Gemma 3 (Local)",
    "provider": "ollama",
    "providerModel": "gemma3",
    "group": "other",
    "trainingStage": "순정 로컬 모델",
    "description": "로컬 Ollama에서 실행하는 Gemma 3",
    "enabled": true,
    "available": true,
    "availabilityMessage": null,
    "isMock": false
  }
]
```

민감 설정값은 반환하지 않는다. 특히 Gemini API 키와 전체 Provider 설정 객체를 응답에 넣지 않는다.

Frontend는 이 응답을 모델 카드의 단일 진실 공급원으로 사용한다. API가 실패했을 때의 재시도·오류 UI를 제공하되 실제로 로드하지 못한 모델을 실행 가능하다고 표시하지 않는다.

### 10.2 단일 실행

기존 Endpoint를 유지한다.

```text
POST /api/admin/llm/run
```

기존 요청:

```json
{
  "prompt": "질문",
  "modelId": "ollama-gemma3",
  "documentName": null
}
```

응답에는 기존 필드를 유지하면서 Provider 식별 정보를 추가한다.

```json
{
  "modelId": "ollama-gemma3",
  "provider": "ollama",
  "providerModel": "gemma3",
  "answer": "실제 모델 응답",
  "responseTimeSeconds": 2.31,
  "inputTokens": 18,
  "outputTokens": 72,
  "totalTokens": 90,
  "finishReason": "stop",
  "isMock": false
}
```

Token 필드는 Provider가 값을 제공하지 않는 경우를 위해 nullable로 확장하고 Frontend도 이를 처리한다.

기존 `/api/admin/llm/compare`가 현재 UI에서 사용되는지 먼저 확인한다. 사용되지 않으면 즉시 삭제하지 말고 deprecated 상태와 테스트 범위를 문서화한다. 사용 중이면 같은 application service를 호출하도록 중복 Mock 로직을 제거한다.

## 11. 오류 계약

Provider SDK 예외를 그대로 Frontend에 노출하지 않는다. 공통 도메인 오류로 변환한 뒤 Router에서 HTTP 상태로 매핑한다.

| 상황 | 권장 HTTP | 사용자 메시지 방향 |
| --- | --- | --- |
| 알 수 없는 Model ID | 422 | 지원하지 않는 모델 |
| Provider 비활성화 또는 API 키 없음 | 503 | 설정되지 않은 모델 |
| Ollama 연결 실패 | 503 | Ollama 실행 상태 확인 |
| Ollama 모델 미설치 | 503 | `ollama pull gemma3` 안내 |
| Provider timeout | 504 | 제한시간 초과 |
| Gemini 인증 실패 | 502 또는 503 | API 키 설정 확인, 키 값은 비노출 |
| Gemini 429 | 429 | 무료 할당량/AI Studio 확인 |
| Gemini 안전 정책 차단 | 422 | 요청이 Provider 정책으로 처리되지 않음 |
| Provider 5xx 또는 잘못된 응답 | 502 | 외부 모델 응답 오류 |

내부 로그에는 Provider, 안전한 Model ID, elapsed time, 오류 종류만 남긴다. Prompt 원문, 모델 답변 전문, API 키, 개인·의료정보는 기본 로그에서 제외한다.

## 12. 동시 실행과 자원 보호

현재 “전체 모델 실행”은 모델별 요청을 병렬로 보낸다. 이를 유지하되 Provider별 동시 실행 제한을 둔다.

- Ollama 기본 동시 실행: 1
- Gemini 기본 동시 실행: 2
- `asyncio.Semaphore` 등으로 Provider 내부에서 제한
- 대기 시간도 전체 timeout 정책에 포함되는지 명확히 정의
- Frontend AbortController 취소가 Provider 추론까지 반드시 중단시킨다고 가정하지 않음

Ollama는 로컬 GPU/메모리를 사용할 수 있으므로 전체 실행이 여러 Ollama 모델을 동시에 로드하지 않게 한다. 향후 모델별 queue가 필요해질 수 있지만 이번 범위에서는 프로세스 내 semaphore로 제한한다.

## 13. Frontend 변경 지침

- `adminOptions.ts`의 LLM 모델 하드코딩을 Backend 모델 목록 기반으로 전환한다.
- OCR 상수는 그대로 유지한다.
- 첫 번째 비교 영역에는 실제 `ollama-gemma3`, `gemini` 두 모델만 표시한다.
- 다른 LLM 비교 영역에는 `medgemma`, `gemma`, `qwen`, `llama` 네 Mock 모델을 표시한다.
- 기존 `main-fine-tuned`, `main-partial` 카드와 상태 초기값을 제거한다.
- 모델 로딩 상태, 목록 조회 오류, Provider unavailable 상태를 표시한다.
- `enabled=false` 또는 `available=false`인 모델은 실행 버튼을 비활성화하고 이유를 노출한다.
- 카드에 `Local Ollama`, `Gemini API`, `Mock` Badge를 표시한다.
- `Mock` 문구를 실제 Provider 카드에서 제거한다.
- Token이 `null`이면 `0`이 아니라 `계산 안 됨`으로 표시한다.
- Gemini 무료 등급 카드에는 민감정보 전송 주의 문구를 표시한다.
- 참고 파일은 현재 파일명만 전달되며 파일 내용이 모델에 반영되지 않는다는 안내를 유지한다.
- 기존 모델별 완료·오류·취소·재실행 상태 전이를 보존한다.

## 14. 설정과 의존성

다음 파일을 일관되게 갱신한다.

- `backend/app/core/config.py`
- 최상위 `.env.example`
- `backend/requirements.txt`
- `README.md`
- `backend/README.md`

권장 신규 직접 의존성:

- `httpx`: Ollama 비동기 REST 호출
- `google-genai`: Gemini 공식 Python SDK

버전 범위는 현재 Python 3.12 및 기존 dependency tree와 호환되는 범위로 고정한다. 설치 후 전체 Backend 테스트로 충돌 여부를 확인한다.

실제 `GEMINI_API_KEY`를 다음 위치에 기록하지 않는다.

- `.env.example`
- README 또는 보고서
- Git commit
- Frontend `.env`
- 테스트 fixture와 snapshot

## 15. 테스트 요구사항

### 15.1 공통 Service/Registry 단위 테스트

- Model ID가 올바른 Provider와 upstream 모델로 해석됨
- 알 수 없는 Model ID 422
- 비활성 모델 실행 거부
- Provider 결과가 공통 응답으로 변환됨
- Token 누락 시 `None` 유지
- Provider exception이 공통 도메인 오류로 변환됨
- Mock 모델과 실제 모델의 `isMock` 값 구분
- `main-fine-tuned`, `main-partial`이 Registry와 모델 목록 응답에 존재하지 않음
- `ollama-gemma3`, `gemini`가 실제 Provider로 해석됨
- `medgemma`, `gemma`, `qwen`, `llama`가 Mock Provider로 해석됨
- Mock 모델의 `provider_key`를 실제 Provider로 바꿨을 때 공통 실행 코드 수정 없이 실제 Provider가 호출됨

### 15.2 Ollama Provider 단위 테스트

실제 네트워크를 사용하지 않고 `httpx.MockTransport` 또는 동등한 방식으로 검증한다.

- `/api/chat` 요청 URL, `model=gemma3`, `stream=false`
- `message.content` 매핑
- `prompt_eval_count`, `eval_count`, 합계 매핑
- 연결 실패
- timeout
- 404 모델 미설치
- JSON 오류 또는 빈 답변
- API 키나 Prompt가 로그에 남지 않음

### 15.3 Gemini Provider 단위 테스트

SDK client를 Mock 주입해 검증한다.

- `client.aio.models.generate_content` 호출
- 환경변수의 모델명 사용
- 실제 usage metadata 매핑
- 빈 응답 처리
- API 키 없음
- 인증 실패
- 429 quota
- safety block
- timeout/5xx
- client close

### 15.4 API 계약 테스트

- `GET /api/admin/llm/models` camelCase 응답
- 비밀값 미포함
- `POST /api/admin/llm/run` 기존 요청 호환
- Provider 필드가 추가된 성공 응답
- nullable Token 응답
- 오류 상태와 메시지 매핑
- 기존 OCR 및 Job 테스트 회귀 없음

### 15.5 실제 로컬 통합 테스트

Mock 단위 테스트와 별도로 개발 PC에서 다음을 수행한다.

1. `ollama list`에서 `gemma3` 확인
2. Ollama API `/api/tags` 확인
3. Backend 실행
4. Frontend Admin LLM 탭의 첫 번째 비교 영역에서 Gemma 3 (Local) 카드 단일 실행
5. 한국어 질문에 실제 답변 표시 확인
6. Input/Output Token과 응답시간 표시 확인
7. 전체 모델 실행 중 Gemma 카드가 독립 완료되는지 확인
8. Ollama 종료 후 명확한 unavailable/error UI 확인

Gemini는 사용자가 직접 로컬 `.env`에 키를 넣은 환경에서 다음을 확인한다.

1. Gemini 카드 available 표시
2. 실제 질문 응답
3. usage metadata 표시
4. 잘못된 키의 안전한 오류 메시지
5. 무료 quota 초과 시 429 UI
6. 로그와 브라우저 응답에 API 키가 없는지 확인

외부 API가 필요한 통합 테스트는 기본 CI에서 자동 실행하지 않는다. 명시적인 환경변수가 있을 때만 실행하거나 수동 integration marker로 분리한다.

## 16. 검증 명령

프로젝트의 실제 실행 환경과 스크립트를 먼저 확인한 뒤 다음 범위를 검증한다.

```powershell
backend\.venv\Scripts\python.exe -m unittest discover -s backend\tests
cd frontend
npm.cmd run build
```

추가로 다음을 확인한다.

- `git diff --check`
- Frontend bundle에 `GEMINI_API_KEY` 문자열 또는 실제 키가 없음
- Backend Mock fixture가 실제 Gemma/Gemini 경로에서 사용되지 않음
- Ollama/Gemini Provider 실패가 다른 모델 카드 상태를 덮어쓰지 않음
- OCR 테스트와 화면에 회귀가 없음

테스트 실행으로 생성되는 캐시·빌드 산출물은 Git 변경사항에 포함하지 않는다.

## 17. 구현 순서

1. 현재 LLM Endpoint와 Frontend 사용 경로를 다시 추적한다.
2. Provider 공통 계약과 도메인 오류를 만든다.
3. Model Registry와 기존 Mock Provider를 분리하고 최종 여섯 모델 구성을 등록한다.
4. Ollama Provider와 단위 테스트를 구현한다.
5. Gemini Provider와 단위 테스트를 구현한다.
6. Application Service에서 공통 실행 흐름을 연결한다.
7. 모델 목록 API와 실행 API를 연결한다.
8. Frontend 모델 목록을 Backend 기준으로 전환하고 기존 Main Model 두 카드를 실제 Gemma 3·Gemini 카드로 교체한다.
9. 실제/Mock/Unavailable Badge와 오류 UI를 갱신한다.
10. Backend 전체 테스트와 Frontend build를 수행한다.
11. 실제 Ollama `gemma3` 통합 테스트를 수행한다.
12. 사용자가 제공한 로컬 Gemini 키 환경에서만 Gemini 통합 테스트를 수행한다.
13. README와 구현 결과 보고서를 작성한다.

## 18. 완료 조건

다음을 모두 충족해야 작업 완료로 판단한다.

- `main-fine-tuned`, `main-partial` Mock 모델이 Backend Registry와 Frontend에서 제거된다.
- 첫 번째 비교 영역에 실제 `ollama-gemma3`, `gemini` 두 모델이 표시된다.
- 다른 LLM 비교 영역에 `medgemma`, `gemma`, `qwen`, `llama` 네 Mock 모델이 표시된다.
- Frontend에서 `ollama-gemma3` 실행 시 Backend가 로컬 Ollama `gemma3`를 실제 호출한다.
- Frontend에서 `gemini` 실행 시 Backend가 Gemini API를 실제 호출한다.
- Gemini API 키가 Backend 밖으로 노출되지 않는다.
- Gemma/Gemini 응답이 Mock 문구나 고정 fixture가 아니다.
- 실제 Provider Token 사용량을 표시하며 알 수 없는 값은 위조하지 않는다.
- Provider 장애가 모델별 오류 카드로 격리된다.
- 개발자가 Registry의 `provider_key`와 `provider_model`을 바꾸는 것만으로 기존 Mock 모델을 지원되는 실제 Provider 모델로 교체할 수 있다.
- 개발자가 Registry 항목만 추가해 같은 Provider의 새 모델을 등록할 수 있다.
- 새로운 Provider 추가 시 Router와 공통 Frontend 실행 Hook을 수정하지 않아도 된다.
- 기존 전체 실행, 개별 실행, 취소, 재실행 동작이 유지된다.
- Backend 전체 테스트와 Frontend production build가 통과한다.
- 실제 Ollama `gemma3` 로컬 통합 테스트가 통과한다.
- Gemini는 키가 있을 때 실제 통합 테스트가 통과하고, 키가 없을 때 안전하게 unavailable로 표시된다.
- 변경 내역과 남은 제한사항을 `docs/2_reports`에 새 보고서로 남긴다.

## 19. 구현 시 금지사항

- Gemini API 키 하드코딩 또는 Frontend 전달
- Frontend에서 Ollama/Gemini 직접 호출
- Model ID를 사용자가 임의 URL 또는 upstream 모델명으로 바꾸게 허용
- Router의 거대한 Provider 분기문
- 문자 길이 기반 Token 수를 실제 Token처럼 표시
- Gemini 무료 등급이 영구 보장된다고 문서화
- Gemini에 참고 파일 내용이 전송되지 않는데 RAG가 적용된 것처럼 표시
- Ollama 모델 자동 다운로드
- 실제 Provider 오류를 모두 500 하나로 처리
- Provider 응답 전문과 의료·개인정보를 로그에 기록
- OCR 코드나 UI를 이 작업 명목으로 불필요하게 수정

## 20. 공식 참고 자료

- [Ollama API 소개](https://docs.ollama.com/api/introduction)
- [Ollama Chat API](https://docs.ollama.com/api/chat)
- [Ollama 로컬 모델 목록 API](https://docs.ollama.com/api/tags)
- [Ollama 오류 계약](https://docs.ollama.com/api/errors)
- [Google GenAI SDK 공식 안내](https://ai.google.dev/gemini-api/docs/libraries)
- [Google GenAI Python SDK](https://github.com/googleapis/python-genai)
- [Gemini API 키 설정](https://ai.google.dev/gemini-api/docs/generate-content/api-key)
- [Gemini 3.5 Flash-Lite 모델](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite)
- [Gemini API Rate Limits](https://ai.google.dev/gemini-api/docs/rate-limits)
- [Gemini 모델 목록 API](https://ai.google.dev/api/models)

구현을 시작할 때 공식 문서가 갱신되었는지 다시 확인하고, 특히 Gemini 모델명·무료 등급·SDK API가 변경됐다면 현재 공식 문서를 우선한다.
