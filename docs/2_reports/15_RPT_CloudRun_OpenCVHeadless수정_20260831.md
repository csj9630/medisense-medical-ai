# Cloud Run OpenCV Headless 전환 작업 완료 보고서

- 작업일: 2026-08-31
- 작업 영역: Backend / OCR / Dependency / Docker / Cloud Run
- 대상 오류: `ImportError: libGL.so.1: cannot open shared object file`
- 작업 범위: OpenCV 의존성 단일화, Docker 패키징 보완, Cloud Run 실행 조건 검증
- 제외 범위: Startup timeout 변경, OCR·LLM 비즈니스 로직 변경, 비밀 환경변수 변경

---

## 1. 원인 분석

Python 런타임 의존성 설치 경로는 다음과 같다.

```text
backend/dockerfile
→ backend/requirements.txt
→ ai/ocr/requirements.txt
→ paddleocr 3.7
→ paddlex[ocr-core] 3.7
→ opencv-contrib-python 4.10.0.84 (GUI wheel)
```

`ai/ocr/requirements.txt`에는 기존에도 `opencv-python-headless`가 있었지만, PaddleX가
GUI용 `opencv-contrib-python`을 별도로 전이 설치했다. 그 결과 OpenCV wheel 두 종류가
동시에 설치되고 GUI wheel의 `cv2`가 선택되어, `libGL.so.1`이 없는 Cloud Run 컨테이너가
애플리케이션 시작 중 exit(1)했다.

추가 감사 결과:

- `pyproject.toml`에는 프로젝트 패키징 정보만 있고 런타임 의존성 선언은 없다.
- Python용 lock 파일(`poetry.lock`, `uv.lock`, `Pipfile.lock` 등)은 없다.
- `frontend/package-lock.json`은 프런트엔드 의존성 파일이므로 Python OpenCV 설치와 무관하다.
- 코드에서 `cv2.imshow`, `waitKey`, `namedWindow` 등 GUI API 사용은 발견되지 않았다.

따라서 `libgl1`을 추가하지 않고 contrib 기능을 유지하는 headless wheel로 전환했다.

---

## 2. 변경 내용

### 2.1 OpenCV 의존성 단일화

`ai/ocr/requirements.txt`의 OpenCV 선언을 다음 단일 패키지로 변경했다.

```text
opencv-contrib-python-headless==4.10.0.84
```

PaddleX가 설치하는 GUI wheel과 ABI 버전을 맞추면서 contrib 모듈을 유지하기 위해 같은
버전의 headless contrib 패키지를 사용한다.

### 2.2 Docker 최종 설치 상태 보정

PaddleX의 패키지 메타데이터가 GUI wheel 이름을 직접 요구하므로 일반적인 constraints만으로
headless 패키지로 대체할 수 없다. Docker 의존성 설치 후 다음 순서로 최종 이미지를 정리했다.

```text
OpenCV 네 종류 모두 제거
→ opencv-contrib-python-headless만 --no-deps로 재설치
→ 빌드 중 import cv2 검증
```

이 방식은 같은 `cv2` 경로를 공유하는 wheel이 중복 설치되는 것을 방지한다.

또한 `app.main`의 실제 import 경로에 포함되는 `ai/consultation`, `ai/rag`를 이미지에 복사하고,
Docker build context에서 제외하던 `ai/rag` 규칙을 제거했다. 로컬 DB와 `.venv` 변형 디렉터리는
이미지에 들어가지 않도록 `.dockerignore`를 보완했다.

Cloud Run 실행 명령은 다음 조건을 명시한다.

```text
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}"
```

---

## 3. 검증 결과

Cloud Run과 동일한 Linux x86_64 기준으로 이미지를 빌드했다.

```text
docker build --platform linux/amd64 -f backend/dockerfile \
  -t thegpt-cloudrun-opencv:test .
```

| 검증 항목 | 결과 |
|---|---|
| Docker 이미지 빌드 | 성공 |
| `python -c "import cv2; print(cv2.__version__)"` | `4.10.0` |
| OpenCV GUI Backend | `GUI: NONE` |
| 최종 OpenCV 배포판 목록 | `opencv-contrib-python-headless==4.10.0.84` 한 개 |
| `from app.main import app` | 성공 (`MediSense API`) |
| `PORT=8080` 애플리케이션 시작 | 성공 |
| Uvicorn 바인딩 | `http://0.0.0.0:8080` |
| `GET /health` | `200 OK`, `{"status":"ok"}` |
| Backend unittest | Python 3.12 환경 2개에서 각각 49개 통과 |
| `git diff --check` | 통과 |

로컬 검증 컨테이너에는 비밀 환경변수를 전달하지 않았으며, 검증 후 종료했다.

---

## 4. 최종 결과

- GUI OpenCV wheel이 더 이상 최종 Docker 이미지에 남지 않는다.
- `cv2`가 `libGL.so.1` 없이 import된다.
- 애플리케이션이 Cloud Run 계약인 `0.0.0.0:${PORT}`에서 정상 시작한다.
- `libgl1` 추가와 startup timeout 증가는 필요하지 않다.
- OCR 및 기타 애플리케이션 비즈니스 로직은 변경하지 않았다.

