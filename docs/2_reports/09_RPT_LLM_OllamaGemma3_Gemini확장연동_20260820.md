# LLM Ollama Gemma 3·Gemini 확장 연동 구현 결과 보고서

## 1. 작업 목적

Admin LLM 비교 화면의 `main-fine-tuned`, `main-partial` Backend Mock을 제거하고 다음 실제 모델로 교체했다.

- 로컬 Ollama 순정 `gemma3`
- Gemini API `gemini-3.5-flash-lite`

`medgemma`, `gemma`, `qwen`, `llama`는 명시적인 Mock 비교군으로 유지했다.

## 2. 최종 모델 구성

| Model ID | Provider | Provider Model | 상태 |
| --- | --- | --- | --- |
| `ollama-gemma3` | `ollama` | `gemma3` | 실제 호출 |
| `gemini` | `gemini` | `gemini-3.5-flash-lite` | 실제 호출 |
| `medgemma` | `mock` | `medgemma` | Mock |
| `gemma` | `mock` | `gemma` | Mock |
| `qwen` | `mock` | `qwen` | Mock |
| `llama` | `mock` | `llama` | Mock 오류 fixture |

## 3. Backend 구조

`backend/app/services/llm`에 다음 책임을 분리했다.

- `contracts.py`: Provider 요청·결과·가용성·도메인 오류
- `registry.py`: Model ID와 Provider/upstream 모델 매핑
- `application.py`: 공통 실행 및 모델 목록 조율
- `providers/ollama.py`: Ollama `/api/chat`, `/api/tags`
- `providers/gemini.py`: `google-genai` 비동기 호출
- `providers/mock.py`: 네 Mock 모델 fixture

Router는 Provider별 분기 없이 Application Service 결과만 HTTP Schema로 변환한다.

## 4. Mock에서 실제 모델로 전환

Model Registry의 다음 두 값이 실행 구현을 결정한다.

```python
provider_key="mock"
provider_model="medgemma"
```

같은 모델을 실제 Ollama에서 실행하려면 다음처럼 Registry를 바꾼다.

```python
provider_key="ollama"
provider_model="실제-ollama-model-tag"
```

`isMock`은 Provider 종류에서 자동 계산하므로 별도 Boolean 설정이 어긋나지 않는다. 기존 Provider를 사용하는 모델 전환에는 Router, Schema, Frontend Hook 수정이 필요하지 않다.

## 5. API와 Frontend

- `GET /api/admin/llm/models`: 여섯 모델의 metadata와 현재 가용성 반환
- `POST /api/admin/llm/run`: Registry가 선택한 실제 또는 Mock Provider 실행
- 기존 `/api/admin/llm/compare`: 같은 Provider 경계를 사용하는 호환 API로 유지

Frontend는 하드코딩된 LLM 모델 목록 대신 Backend 모델 목록을 사용한다. 첫 영역에는 실제 두 모델, 다른 LLM 영역에는 네 Mock 모델을 표시한다. 실제/Mock Badge, Provider 미설정·미설치 메시지, nullable Token 표시를 추가했다.

## 6. 환경변수 통합

Backend와 Frontend의 실제 설정은 프로젝트 최상위 `.env` 하나를 사용한다. `VITE_API_URL`은 최상위 `.env.example`에 포함하고, `frontend/.env.example`도 Frontend 협업자를 위한 예제 파일로 유지한다. Vite의 `envDir`은 프로젝트 최상위를 가리키며 브라우저에는 `VITE_` 접두사만 노출한다.

Gemini API 키는 `GEMINI_API_KEY`로 Backend에만 전달한다. 실제 키는 코드, 예제 파일, 응답, 로그에 포함하지 않는다.

## 7. 오류 및 자원 보호

- Ollama 연결 실패·모델 미설치: 503
- Provider timeout: 504
- Gemini 인증 실패: 503
- Gemini quota: 429
- 안전 정책 차단: 422
- upstream 오류: 502

Provider별 semaphore를 적용해 Ollama 기본 1개, Gemini 기본 2개 동시 실행으로 제한했다. Frontend 취소는 브라우저 요청 상태를 취소하지만 Provider 추론 자체가 계속될 가능성을 UI 메시지에 반영했다.

## 8. 검증 결과

- Python 전체 소스 문법 검사: 통과
- LLM Provider·Registry 단위 테스트: 7개 통과
- 실제 FastAPI Admin LLM API 계약 테스트: 2개 통과
- Frontend TypeScript 검사: 통과
- Vite production build: 통과, 1,877개 모듈 변환
- `git diff --check`: 통과
- 실제 환경설정은 최상위 `.env`를 사용하고 Frontend 예제 파일은 유지함을 확인

LLM 테스트 9개는 프로젝트 밖의 임시 Python 3.14 환경에서 필요한 최소 패키지만 설치해 실행했고 모두 통과했다. 검증 후 임시 환경은 삭제했다.

현재 작업 PC의 PATH에서는 Ollama를 찾지 못했고, 기존 `backend/.venv`는 다른 PC의 Python 3.12 경로를 가리켜 실행되지 않았다. 따라서 실제 Ollama·Gemini 통합 호출과 Backend 전체 테스트는 이 PC에서 완료하지 못했다. Python 3.12 가상환경을 재생성하고 requirements를 설치한 뒤 추가 검증해야 한다.

## 9. 남은 실제 통합 검증

1. Python 3.12로 `backend/.venv` 재생성
2. `backend/requirements.txt` 설치
3. `ollama pull gemma3`
4. Backend 전체 테스트 실행
5. Admin LLM에서 실제 Gemma 3 한국어 응답과 Token 확인
6. 개발자별 `GEMINI_API_KEY` 설정 후 Gemini 실제 호출 확인
7. 잘못된 키, 429, Ollama 종료 상태의 UI 확인

## 10. 보안 및 개인정보

Gemini 실행 시 질문은 외부 API로 전송된다. 무료 등급에는 민감한 의료·개인정보를 입력하지 않도록 UI와 README에 안내했다. 현재 참고 파일은 업로드하지 않으며 파일명만 요청 조건으로 전달한다.
