# Gemini API Key 환경변수 로딩 흐름 정리

- 작성일: 2026-08-20
- 범위: 프로젝트 최상위 `.env`에서 Gemini API 호출까지
- 작업 조건: 문서 외 소스·설정 파일 수정 없음

## 1. 전체 흐름

```text
프로젝트 최상위 .env
  │
  │ GEMINI_API_KEY
  ▼
Pydantic Settings
  │ settings.gemini_api_key
  ▼
LLM Application 생성
  │ api_key 인자
  ▼
GeminiLlmProvider
  │ self._api_key
  ▼
google.genai.Client(api_key=...)
  │
  ▼
Gemini API generate_content 요청
```

키는 Backend 내부에서만 이 경로를 이동한다. Frontend, 모델 목록 응답, 모델 실행 응답에는 키를 전달하지 않는다.

## 2. 최상위 `.env` 설정

실제 환경변수는 프로젝트 최상위 `.env` 하나에서 관리한다.

```dotenv
LLM_GEMINI_ENABLED=true
GEMINI_API_KEY=실제_API_KEY
LLM_GEMINI_MODEL=gemini-3.5-flash-lite
LLM_GEMINI_TIMEOUT_SECONDS=60
LLM_GEMINI_MAX_CONCURRENCY=2
```

주의사항:

- `GEMINI_API_KEY`에 `VITE_` 접두사를 붙이지 않는다.
- 실제 키를 `.env.example`에 기록하지 않는다.
- 실제 `.env`를 Git에 커밋하지 않는다.
- `frontend/.env`가 아니라 프로젝트 최상위 `.env`에 기록한다.
- `.env` 변경 후에는 Backend를 재시작한다.

Gemini를 사용하지 않는 개발 PC에서는 다음과 같이 명시할 수 있다.

```dotenv
LLM_GEMINI_ENABLED=false
GEMINI_API_KEY=
```

## 3. 최상위 `.env` 경로 결정

`backend/app/core/paths.py`가 실행 디렉터리와 무관한 프로젝트 경로를 계산한다.

```python
PROJECT_ROOT = Path(__file__).resolve().parents[3]
ROOT_ENV_FILE = PROJECT_ROOT / ".env"
```

파일 위치를 기준으로 계산하므로 다음 실행 방식 모두 같은 최상위 `.env`를 읽는다.

```text
프로젝트 루트에서 run.bat 실행
Backend 폴더에서 uvicorn 실행
IDE에서 Backend 실행
테스트에서 Backend 모듈 import
```

## 4. Pydantic Settings 로딩

`backend/app/core/config.py`는 `ROOT_ENV_FILE`을 Pydantic Settings의 환경 파일로 지정한다.

```python
model_config = SettingsConfigDict(
    env_file=ROOT_ENV_FILE,
    env_file_encoding="utf-8",
    extra="ignore",
)
```

Gemini 관련 필드는 다음과 같다.

```python
llm_gemini_enabled: bool = True
gemini_api_key: str | None = None
llm_gemini_model: str = "gemini-3.5-flash-lite"
llm_gemini_timeout_seconds: float = 60.0
llm_gemini_max_concurrency: int = 2
```

Pydantic이 환경변수 이름을 Settings 필드에 대응시킨다.

| `.env` 변수                  | Settings 필드                         | 키 미설정 시 기본값 |
| ---------------------------- | ------------------------------------- | ------------------- |
| `LLM_GEMINI_ENABLED`         | `settings.llm_gemini_enabled`         | `True`              |
| `GEMINI_API_KEY`             | `settings.gemini_api_key`             | `None`              |
| `LLM_GEMINI_MODEL`           | `settings.llm_gemini_model`           | `gemini-3.5-flash-lite`  |
| `LLM_GEMINI_TIMEOUT_SECONDS` | `settings.llm_gemini_timeout_seconds` | `60.0`              |
| `LLM_GEMINI_MAX_CONCURRENCY` | `settings.llm_gemini_max_concurrency` | `2`                 |

Settings 객체는 캐시된다.

```python
@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
```

따라서 실행 중 `.env`만 수정해도 기존 `settings`와 Provider에는 자동 반영되지 않는다. Backend 프로세스를 재시작해야 한다.

## 5. LLM Application과 Provider 생성

`backend/app/services/admin_llm.py`가 Backend 모듈 초기화 시 LLM Application을 생성한다.

```python
GeminiLlmProvider(
    enabled=settings.llm_gemini_enabled,
    api_key=settings.gemini_api_key,
    timeout_seconds=settings.llm_gemini_timeout_seconds,
    max_concurrency=settings.llm_gemini_max_concurrency,
)
```

그 결과 다음 값이 Provider 생성자로 전달된다.

```text
settings.llm_gemini_enabled
settings.gemini_api_key
settings.llm_gemini_timeout_seconds
settings.llm_gemini_max_concurrency
```

생성된 LLM Application은 모듈 전역에 보관된다.

```python
llm_application = create_llm_application()
```

이 구조 역시 `.env` 변경 후 Backend 재시작이 필요한 이유다.

## 6. Gemini Provider 내부 보관

`backend/app/services/llm/providers/gemini.py`는 전달받은 키를 다음과 같이 보관한다.

```python
self._api_key = api_key.strip() if api_key else None
```

앞뒤 공백은 제거하고, 키가 없거나 빈 문자열이면 `None`으로 처리한다.

모델 목록을 조회할 때 키가 없으면 Backend 전체를 중단하지 않고 Gemini 모델만 unavailable 상태로 반환한다.

```python
if not self._api_key:
    return ProviderAvailability(
        False,
        "최상위 .env에 GEMINI_API_KEY를 설정하세요.",
    )
```

따라서 키가 없는 경우의 기대 동작은 다음과 같다.

```text
Backend 시작 성공
Ollama 및 Mock 모델 사용 가능
Gemini 카드 비활성화
Gemini 실행 요청 시 Provider unavailable 오류
```

## 7. Google Gen AI Client 생성

사용자가 Gemini 모델 실행을 요청하면 Provider가 저장된 키로 Google Client를 만든다.

```python
client = self._client_factory(self._api_key)
async_client = client.aio
```

기본 Client Factory는 다음과 같다.

```python
def _create_google_client(api_key: str) -> Any:
    from google import genai
    return genai.Client(api_key=api_key)
```

최종적으로 키가 Google SDK에 전달되는 지점은 다음 한 줄이다.

```python
genai.Client(api_key=api_key)
```

## 8. Gemini API 호출

Provider는 Registry가 선택한 실제 모델 ID와 사용자의 프롬프트로 비동기 요청을 수행한다.

```python
response = await async_client.models.generate_content(
    model=model.provider_model,
    contents=request.prompt,
)
```

현재 기본 모델 흐름은 다음과 같다.

```text
.env의 LLM_GEMINI_MODEL
  → settings.llm_gemini_model
  → Model Registry의 provider_model
  → generate_content(model=...)
```

`GEMINI_API_KEY`는 요청 인증에 사용되고 `LLM_GEMINI_MODEL`은 호출할 모델을 선택하는 데 사용된다.

## 9. 요청 종료와 자원 정리

Gemini 호출 성공·실패·timeout과 무관하게 `finally`에서 Client를 닫는다.

```python
finally:
    await self._close_clients(async_client, client)
```

현재 구현은 다음 두 자원을 각각 정리한다.

```text
async_client.aclose()
client.close()
```

키는 Provider 인스턴스에 문자열로 보관되지만 API 응답으로 직렬화하지 않으며 완료 로그에도 포함하지 않는다.

## 10. Frontend와의 보안 경계

Frontend는 Gemini 키를 읽거나 전달하지 않는다.

```text
Frontend
  → modelId, prompt, documentName 전송
Backend
  → 내부 settings에서 GEMINI_API_KEY 조회
  → Gemini API 호출
```

Vite가 Client에 노출하는 환경변수는 `VITE_` 접두사 변수다. 따라서 다음과 같이 구분한다.

```dotenv
# Frontend 공개 설정
VITE_API_URL=http://localhost:8000/api

# Backend 전용 비밀값
GEMINI_API_KEY=실제_API_KEY
```

절대로 다음처럼 작성하면 안 된다.

```dotenv
VITE_GEMINI_API_KEY=실제_API_KEY
```

`VITE_`가 붙은 값은 Frontend 번들에 포함될 수 있어 사용자가 확인할 수 있다.

## 11. 오류별 흐름

### 키가 없는 경우

```text
GEMINI_API_KEY 미설정
  → settings.gemini_api_key = None
  → GeminiLlmProvider._api_key = None
  → 모델 목록에서 unavailable
  → 실행 시 503 계열 Provider unavailable
```

### 키가 잘못된 경우

```text
문자열은 존재
  → 모델 목록에서는 현재 available로 표시될 수 있음
  → 실제 generate_content 호출
  → Google 인증 오류
  → 안전한 인증 실패 메시지로 변환
```

현재 availability 검사는 키 문자열과 SDK 설치 여부만 확인하며 실제 키 유효성은 실행 시 확인한다는 한계가 있다.

### 무료 할당량을 초과한 경우

```text
Gemini API 429
  → Provider가 상태 코드 확인
  → LlmProviderRateLimitError
  → Backend HTTP 429
  → Frontend 모델 카드 오류 표시
```

### 요청 제한시간을 초과한 경우

```text
asyncio.wait_for timeout
  → LlmProviderTimeoutError
  → Backend HTTP 504
  → Client 정리
```

## 12. 확인 절차

키 값을 출력하지 않고 설정 여부만 확인해야 한다.

1. 최상위 `.env`에 `GEMINI_API_KEY`가 있는지 확인한다.
2. Backend를 완전히 재시작한다.
3. `GET /api/admin/llm/models`에서 Gemini의 `available` 값을 확인한다.
4. Admin 화면에서 개인정보가 없는 짧은 테스트 프롬프트로 Gemini만 실행한다.
5. 401/403이면 키와 권한을 확인한다.
6. 429이면 Google AI Studio의 현재 무료 할당량을 확인한다.

디버깅 시에도 다음 정보는 출력하지 않는다.

```text
GEMINI_API_KEY 전체 값
Google Client 내부 인증 헤더
실제 키가 포함될 수 있는 예외 객체 전체 dump
```

## 13. 요약

```text
최상위 .env
  GEMINI_API_KEY
       │
       ▼
backend/app/core/paths.py
  ROOT_ENV_FILE
       │
       ▼
backend/app/core/config.py
  settings.gemini_api_key
       │
       ▼
backend/app/services/admin_llm.py
  GeminiLlmProvider(api_key=...)
       │
       ▼
backend/app/services/llm/providers/gemini.py
  self._api_key
       │
       ▼
google.genai.Client(api_key=...)
       │
       ▼
Gemini API
```

핵심 원칙은 다음 세 가지다.

1. 실제 키는 최상위 `.env`에만 저장한다.
2. Backend가 키를 읽고 Google SDK에 직접 전달한다.
3. Frontend와 API 응답에는 키를 전달하지 않는다.
