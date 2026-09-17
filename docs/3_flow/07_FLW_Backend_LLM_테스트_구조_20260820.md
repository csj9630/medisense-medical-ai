# Backend LLM 테스트 구조와 실행 흐름

> 대상: `backend/tests` 폴더와 `backend/tests/test_admin_llm.py`  
> 작성일: 2026-08-20  
> 목적: Backend 테스트 코드의 역할과 LLM 테스트의 검증 범위 설명

## 1. `backend/tests` 폴더의 역할

`backend/tests`는 Backend 기능을 자동으로 검증하는 테스트 코드 폴더다. 애플리케이션의 실제 서비스 요청을 처리하는 실행 코드가 아니라, 코드 변경 후 기존 동작이 망가지지 않았는지 확인하는 안전망이다.

현재 주요 구성은 다음과 같다.

| 파일 | 검증 대상 |
| --- | --- |
| `test_admin_llm.py` | LLM Registry, Ollama/Gemini Provider, 관리자 LLM API |
| `test_config_paths.py` | 환경설정 및 프로젝트 경로 |
| `test_hybrid_ocr.py` | Hybrid OCR 처리 |
| `test_ocr_jobs.py` | OCR 작업 생성 및 상태 전이 |
| `__init__.py` | `tests` 폴더를 Python 패키지로 인식시키는 파일 |
| `__pycache__` | Python이 자동 생성하는 바이트코드 캐시 |

`__pycache__`는 사람이 작성한 소스가 아니며 Python 실행 과정에서 다시 생성될 수 있다.

## 2. `test_admin_llm.py`의 역할

`backend/tests/test_admin_llm.py`는 관리자 페이지에서 사용하는 LLM 연동 구조가 정해진 계약대로 작동하는지 검증한다.

전체 흐름은 다음과 같다.

```text
테스트용 모델 정의 생성
  -> 테스트용 Provider 또는 Mock HTTP 응답 준비
  -> Registry/Application/Provider/API 호출
  -> 실제 반환값과 예상값 비교
  -> 불일치하면 테스트 실패
```

이 파일은 다음 네 영역을 검사한다.

1. Model Registry 및 Provider Registry
2. Ollama Provider
3. Gemini Provider
4. 관리자 LLM HTTP API

## 3. 공통 테스트 도구

### 3.1 `model_definition()`

테스트에 필요한 `LlmModelDefinition`을 간단히 생성하는 보조 함수다.

기본값은 다음과 같다.

```text
model_id      = ollama-gemma3
provider_key  = ollama
provider_model = gemma3:1b
group         = main
```

각 테스트는 필요한 값만 바꿔서 Ollama, Gemini 또는 Mock 모델을 구성한다.

### 3.2 `FakeProvider`

실제 Ollama나 Gemini를 호출하지 않고 일정한 응답을 반환하는 테스트 전용 Provider다.

```text
answer        = "{provider key} answer"
input_tokens  = 10
output_tokens = 20
total_tokens  = 30
finish_reason = stop
```

이를 통해 외부 서버 상태와 관계없이 Application 및 API 계층의 동작을 빠르고 반복 가능하게 검증한다.

## 4. Registry 및 Application 테스트

`RegistryAndApplicationTest`는 LLM 확장 구조의 핵심 규칙을 확인한다.

### 4.1 최종 모델 구성

모델 목록이 다음 순서와 Provider 연결을 갖는지 검사한다.

| 모델 ID | Provider | 형태 |
| --- | --- | --- |
| `ollama-gemma3` | `ollama` | 실제 연동 |
| `gemini` | `gemini` | 실제 연동 |
| `medgemma` | `mock` | Mock |
| `gemma` | `mock` | Mock |
| `qwen` | `mock` | Mock |
| `llama` | `mock` | Mock |

이전에 제거하기로 한 `main-fine-tuned`, `main-partial`이 Registry에 남아 있지 않은지도 확인한다.

### 4.2 Mock과 실제 Provider 교체 가능성

동일한 모델 ID에서 `provider_key`를 `mock`에서 `ollama`로 바꿨을 때 Application 코드를 변경하지 않아도 다른 Provider가 선택되는지 검사한다.

```text
모델 정의의 provider_key = mock
  -> Mock Provider 실행

모델 정의의 provider_key = ollama
  -> Ollama Provider 실행
```

이 테스트는 향후 Mock 모델을 실제 API 모델로 교체할 수 있는 Registry 구조를 검증한다.

### 4.3 알 수 없는 모델 차단

Registry에 등록되지 않은 모델 ID를 요청하면 `UnknownLlmModelError`가 발생하는지 확인한다.

## 5. Ollama Provider 테스트

`OllamaProviderTest`는 실제 네트워크 대신 `httpx.MockTransport`로 Ollama API 응답을 흉내 낸다.

검증 흐름:

```text
GET /api/tags Mock 응답
  -> gemma3:1b 설치 여부 판정
  -> POST /api/chat Mock 응답
  -> 응답 텍스트와 토큰 수 변환
```

주요 검증 항목은 다음과 같다.

- 요청 모델이 정확히 `gemma3:1b`인지
- 스트리밍을 사용하지 않는 요청인지
- 응답 텍스트가 내부 결과 객체로 전달되는지
- Ollama의 입력·출력 토큰 수가 정확히 매핑되는지
- 모델 목록에 대상 태그가 없을 때 `available=false`가 되는지
- 미설치 안내 메시지가 반환되는지

## 6. Gemini Provider 테스트

`GeminiProviderTest`는 Google SDK의 비동기 클라이언트를 `AsyncMock`으로 대체한다.

정상 흐름:

```text
ProviderGenerateRequest
  -> Gemini async generate_content 호출
  -> text 및 usage_metadata 수신
  -> ProviderGenerateResult로 변환
  -> async client 및 client 정리
```

주요 검증 항목:

- SDK 호출에 `gemini-3.5-flash-lite`가 전달되는지
- 질문이 `contents`로 전달되는지
- 응답 텍스트와 토큰 사용량이 올바르게 변환되는지
- 비동기 클라이언트의 `aclose()`가 호출되는지
- 동기 클라이언트의 `close()`도 호출되는지
- 429 오류가 할당량 오류로 변환되는지
- 404 오류가 설정된 모델을 안내하는 가용성 오류로 변환되는지
- 예외 메시지에 Gemini API 키가 포함되지 않는지

## 7. 관리자 LLM API 테스트

`AdminLlmApiTest`는 FastAPI `TestClient`로 실제 HTTP 계약에 가까운 형태를 검사한다.

테스트용 FastAPI 애플리케이션에 관리자 Router를 연결한 뒤, 전역 `llm_application`을 테스트용 Application으로 교체한다.

검증 API:

```text
GET  /api/admin/llm/models
POST /api/admin/llm/run
```

확인 항목:

- 모델 목록 API가 6개 모델을 반환하는지
- Ollama와 Gemini가 실제 Provider로 표시되는지
- 나머지 4개 모델이 Mock으로 표시되는지
- 응답 필드가 Frontend 계약인 camelCase인지
- API 응답에 `apiKey`가 노출되지 않는지
- 실행 결과에 Provider, Provider 모델, Mock 여부, 토큰 수가 포함되는지
- 제거된 모델 또는 알 수 없는 모델 요청이 HTTP 422로 거부되는지

## 8. 이 테스트가 보장하는 것과 보장하지 않는 것

### 보장하는 범위

- Registry의 모델 및 Provider 연결 규칙
- Provider 요청·응답 변환 로직
- 주요 오류 코드 변환
- 비동기 클라이언트 정리 호출
- API 응답 구조
- API 키 비노출 규칙
- Mock 모델을 실제 Provider로 교체할 수 있는 구조

### 보장하지 않는 범위

- 현재 PC에서 Ollama 서비스가 실행 중인지
- `gemma3:1b`가 실제로 설치되어 있는지
- 실제 Gemini API 키가 유효한지
- Gemini 무료 할당량이 남아 있는지
- 방화벽, 프록시 또는 DNS가 외부 통신을 허용하는지
- Google API가 현재 정상 운영 중인지

테스트에서는 `FakeProvider`, `AsyncMock`, `httpx.MockTransport`를 사용하기 때문이다. 따라서 자동 테스트 통과와 실제 연동 성공은 별도로 판단해야 한다.

## 9. 테스트 단계 구분

```text
단위 테스트
  test_admin_llm.py
  -> 외부 서버 없이 내부 로직 검증

통합 테스트
  실행 중인 Backend + 로컬 Ollama
  -> 실제 모델 설치 및 로컬 호출 검증

외부 연동 테스트
  실행 중인 Backend + Gemini API
  -> 실제 키, 권한, 할당량, 네트워크 검증
```

권장 검증 순서는 단위 테스트, 로컬 Ollama 통합 테스트, Gemini 외부 연동 테스트 순이다. 앞 단계가 실패하면 다음 단계로 넘어가기 전에 내부 코드와 설정 문제를 먼저 해결할 수 있다.

## 10. 관련 파일

- `backend/tests/test_admin_llm.py`
- `backend/app/services/admin_llm.py`
- `backend/app/services/llm/application.py`
- `backend/app/services/llm/contracts.py`
- `backend/app/services/llm/registry.py`
- `backend/app/services/llm/providers/ollama.py`
- `backend/app/services/llm/providers/gemini.py`
- `backend/app/api/admin/router.py`

