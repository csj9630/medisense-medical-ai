# LLM Ollama/Gemini 연동 트러블슈팅

> 상태: 2026-08-20 로컬 개발 PC에서 발생한 Ollama 모델 미탐지 및 Gemini 502 오류의 원인 분석, 수정 내용, 복구 절차를 기록한다.

작성일: 2026-08-20  
대상: 관리자 LLM 모델 목록 및 실행 API, 로컬 Ollama Gemma 3, Google Gemini API

## 1. 장애 증상

관리자 모델 목록 API에서 다음과 같은 불일치가 관찰되었다.

```text
ollama-gemma3
  providerModel: gemma3
  available: false
  availabilityMessage: Ollama 모델이 설치되지 않았습니다: gemma3

gemini
  label: Gemini 3.5 Flash-lite
  providerModel: gemini-2.5-flash
  available: true
  실행 결과: HTTP 502
```

동시에 브라우저에서 `http://127.0.0.1:11434/`에 접속하면 `Ollama is running`이 표시되었다. 이 응답은 Ollama 서버 프로세스가 동작한다는 뜻일 뿐, 설정한 모델 태그가 설치되어 있다는 뜻은 아니다.

## 2. 결론 요약

| 영역 | 직접 원인 | 조치 |
| --- | --- | --- |
| Ollama 모델 미탐지 | 설치된 태그는 `gemma3:1b`인데 Backend 설정은 `gemma3`였음 | 모델 ID를 실제 태그인 `gemma3:1b`로 일치시킴 |
| Gemini 구 모델 표시 | Backend가 `.env` 변경 전에 생성한 캐시된 Settings와 Provider 인스턴스를 계속 사용 | 모델 ID를 `gemini-3.5-flash-lite`로 변경하고 Backend를 완전히 재시작 |
| Gemini 502 원인 확인 곤란 | Gemini의 404 등 일부 응답이 일반적인 502 메시지로 축약되고 원인 로그가 부족했음 | 안전한 상태 로그와 404 모델 오류 매핑을 추가 |
| Backend 재시작 실패 | `backend/.venv`가 이 PC에 없는 Python 3.12 경로를 참조 | Python 3.12 확인 후 가상환경 재생성 필요 |

핵심적으로 다음 네 상태를 서로 구분해야 한다.

1. Ollama 서비스가 실행 중인가
2. 요청할 정확한 Ollama 모델 태그가 설치되어 있는가
3. Backend가 현재 `.env` 설정을 읽어 새 Provider를 생성했는가
4. 외부 Gemini API가 현재 키·모델·할당량으로 실제 호출 가능한가

## 3. Ollama 원인 분석

### 3.1 서버 실행 여부와 모델 설치 여부는 별개다

Ollama 루트 응답은 정상적이었다.

```text
GET http://127.0.0.1:11434/
Ollama is running
```

그러나 모델 목록인 `GET /api/tags`에는 다음 태그만 존재했다.

```text
name:  gemma3:1b
model: gemma3:1b
```

설정값 `gemma3`로 Ollama에 직접 요청하면 다음 결과가 재현되었다.

```text
HTTP 404
{"error":"model 'gemma3' not found"}
```

Provider의 가용성 확인은 설정된 모델명과 설치된 태그를 비교한다. 따라서 설치된 태그가 `gemma3:1b`라면 설정도 정확히 `gemma3:1b`여야 한다.

### 3.2 확인 명령

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:11434/
Invoke-RestMethod http://127.0.0.1:11434/api/tags
ollama list
```

설치된 태그와 `.env`의 값을 비교한다.

```dotenv
LLM_OLLAMA_BASE_URL=http://127.0.0.1:11434
LLM_OLLAMA_MODEL=gemma3:1b
```

다른 크기의 Gemma 3를 사용할 경우에도 `ollama list`에 표시되는 정확한 태그를 설정해야 한다.

## 4. Gemini 원인 분석

### 4.1 화면의 라벨과 실제 Provider 모델은 다를 수 있다

화면에는 `Gemini 3.5 Flash-Lite` 라벨이 표시되더라도, 실제 호출 모델은 API 응답의 `providerModel`이다. 장애 당시 이 값이 `gemini-2.5-flash`였으므로 실행 중인 Backend는 이전 설정을 사용하고 있었다.

현재 의도한 설정은 다음과 같다.

```dotenv
LLM_GEMINI_MODEL=gemini-3.5-flash-lite
LLM_GEMINI_API_KEY=발급받은_API_KEY
```

Gemini 키는 Backend에서만 읽으며 Frontend 코드나 `VITE_*` 환경 변수에 넣지 않는다. `.env.example`에는 실제 키가 아닌 빈 예시 값만 유지한다.

### 4.2 `.env` 변경 후 Backend 완전 재시작이 필요한 이유

설정과 LLM 애플리케이션은 프로세스 수명 동안 재사용된다.

- `backend/app/core/config.py`: `get_settings()`가 `lru_cache`를 사용한다.
- `backend/app/services/admin_llm.py`: 모듈 로드 시 전역 `llm_application`을 생성한다.

따라서 `.env`를 바꾸는 것만으로 이미 실행 중인 프로세스의 설정과 Provider가 갱신되지는 않는다. 파일 감시 개발 서버도 `.env` 변경을 항상 재시작 조건으로 취급한다고 가정해서는 안 된다.

재시작 후 다음 API에서 실제 로드된 모델을 확인한다.

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/api/admin/llm/models
```

기대 결과:

```text
ollama-gemma3.providerModel = gemma3:1b
ollama-gemma3.available     = true
gemini.providerModel        = gemini-3.5-flash-lite
```

재시작 후에도 구 모델명이 나오면 다음을 확인한다.

1. 다른 터미널이나 IDE에서 이전 Backend 프로세스가 남아 있는지 확인한다.
2. 브라우저가 요청하는 API 포트와 현재 실행한 Backend 포트가 같은지 확인한다.
3. 다른 작업 사본의 Backend를 실행하고 있지 않은지 확인한다.
4. Process/User/Machine 범위의 `LLM_*` 환경 변수가 `.env`를 덮어쓰지 않는지 확인한다.

이번 점검에서는 OS Process/User/Machine 범위의 `LLM_*` 덮어쓰기 값은 발견되지 않았다.

### 4.3 `available: true`는 원격 호출 성공을 보장하지 않는다

Gemini의 로컬 가용성 검사는 주로 API 키 설정 여부와 필요한 패키지 존재 여부를 판단한다. 다음 원격 상태까지 미리 보장하지는 않는다.

- API 키가 유효한지
- 해당 키가 모델을 호출할 권한이 있는지
- 모델명이 API에서 유효한지
- 무료 할당량이 남아 있는지
- 현재 네트워크에서 Google API에 접근 가능한지

따라서 `available: true`인 상태에서도 실행 요청은 실패할 수 있다.

## 5. Gemini 오류 코드별 추적

Gemini Provider에는 비밀값을 기록하지 않는 안전한 오류 로그와 404 모델 오류 구분을 추가했다. 로그에는 모델명, 예외 유형, HTTP 상태 코드, Provider 상태만 남기고 API 키와 요청 본문은 남기지 않는다.

| 상태 | 우선 확인할 원인 | 권장 조치 |
| --- | --- | --- |
| 400 | 잘못된 요청 형식·모델 파라미터 | Backend 로그와 요청 스키마 확인 |
| 401 | API 키 오류 | 키 오탈자·폐기 여부 확인 후 Backend 재시작 |
| 403 | 권한·지역·프로젝트 정책 | Google 프로젝트 및 API 사용 권한 확인 |
| 404 | 모델 ID가 없거나 접근 불가 | `LLM_GEMINI_MODEL`과 지원 모델 확인 |
| 429 | 무료 할당량 또는 속도 제한 | 할당량 확인, 재시도 간격 적용 |
| 5xx | Google 상위 서비스 장애 | 잠시 후 재시도하고 상태 페이지 확인 |
| Timeout/Network | DNS·방화벽·프록시·인터넷 연결 | 서버 실행 환경의 외부 통신 확인 |

Frontend에는 내부 예외나 API 키를 노출하지 않고 Backend가 정제한 메시지만 반환해야 한다.

## 6. Python 가상환경 문제와 Backend 복구

현재 PC의 기존 `backend/.venv`는 다음과 같은 존재하지 않는 인터프리터 경로를 참조했다.

```text
C:\Users\tmdwn\AppData\Local\Programs\Python\Python312\python.exe
```

따라서 소스 변경으로 이전 개발 서버가 종료된 뒤 자동으로 다시 시작되지 못했다. 먼저 Python 3.12가 설치되어 있는지 확인하고, 기존 환경은 즉시 삭제하지 말고 이름을 바꿔 보존한 다음 재생성한다.

```powershell
py -3.12 --version
Rename-Item backend\.venv backend\.venv.broken
py -3.12 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\run.bat
```

주의 사항:

- `backend/.venv.broken`이 이미 존재하는지 먼저 확인한다.
- Python 3.12 확인이 실패하면 가상환경을 이동하거나 삭제하지 않는다.
- 가상환경과 실제 `.env`는 Git에 커밋하지 않는다.
- 복구 후 `/health`와 모델 목록 API를 다시 확인한다.

## 7. 적용된 코드 및 설정 변경

이번 장애 대응에서 다음 항목을 반영했다.

- `backend/app/core/config.py`
  - 기본 Ollama 모델: `gemma3:1b`
  - 기본 Gemini 모델: `gemini-3.5-flash-lite`
  - 임시 Settings 디버그 출력 제거
- `.env.example`
  - 두 Provider의 현재 모델 ID 반영
- `backend/app/services/llm/registry.py`
  - Gemini 표시 라벨 갱신
- `backend/app/services/llm/providers/gemini.py`
  - 비밀값을 제외한 오류 로그 추가
  - 404를 설정 모델 오류로 구분해 안내
- `backend/tests/test_admin_llm.py`
  - 새 기본 모델 ID와 Gemini 404 매핑 테스트 반영

실제 `.env`의 API 키는 수정하거나 출력하지 않았다.

## 8. 검증 결과

프로젝트의 손상된 `backend/.venv` 대신 격리된 임시 환경에서 다음을 검증했다.

| 검증 항목 | 결과 |
| --- | --- |
| LLM 관련 자동 테스트 | 10개 모두 통과 |
| Settings의 Ollama 모델 | `gemma3:1b` |
| Settings의 Gemini 모델 | `gemini-3.5-flash-lite` |
| Gemini 키 로드 여부 | 설정됨. 값 자체는 출력하지 않음 |
| Provider Registry의 Ollama 가용성 | `true` |
| 로컬 Ollama 실제 생성 요청 | 성공, 응답 및 토큰 사용량 반환 |
| TestClient 모델 목록 API | HTTP 200, 두 새 모델 ID 확인 |
| TestClient Ollama 실행 API | HTTP 200, `gemma3:1b` 응답 확인 |

로컬 Ollama 실제 호출에서는 응답이 존재했고 입력 15, 출력 3, 전체 18 토큰과 `finish_reason=stop`이 확인되었다.

외부 Gemini 실호출은 이번 검증 범위에서는 실행하지 않았다. 따라서 코드의 모델 ID 반영과 오류 처리까지는 확인됐지만, 사용 중인 실제 키의 유효성·권한·무료 할당량·네트워크 상태는 Backend 가상환경 복구 및 재시작 후 별도로 확인해야 한다.

## 9. 빠른 복구 순서

```text
1. ollama list에서 gemma3:1b 설치 확인
2. 최상위 .env의 두 모델 ID와 Gemini 키 설정 여부 확인
3. backend/.venv가 현재 PC의 Python을 참조하는지 확인
4. Backend 완전 재시작
5. /health 확인
6. /api/admin/llm/models의 providerModel 확인
7. Ollama 실행 API 확인
8. Gemini 실행 API 확인
9. 실패 시 Backend 로그의 HTTP 상태 코드로 원인 분류
```

## 10. 관련 파일 및 참고 자료

관련 구현 파일:

- `backend/app/core/config.py`
- `backend/app/core/paths.py`
- `backend/app/services/admin_llm.py`
- `backend/app/services/llm/providers/ollama.py`
- `backend/app/services/llm/providers/gemini.py`
- `backend/tests/test_admin_llm.py`
- `.env.example`

공식 참고 자료:

- [Ollama List models API](https://docs.ollama.com/api/tags)
- [Ollama Chat API](https://docs.ollama.com/api/chat)
- [Gemini 3.5 Flash-Lite 모델 문서](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite)

