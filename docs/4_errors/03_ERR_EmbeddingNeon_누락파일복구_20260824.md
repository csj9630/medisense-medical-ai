# Embedding·Neon 저장 누락 파일 복구 결과 보고서

- 작업일: 2026-08-24
- 작업 영역: Backend / FastAPI / OCR Vector 저장
- 대상 기능: OCR Chunk Gemini Embedding 및 Neon PostgreSQL 저장
- 주요 기술: Python 3.12, FastAPI, SQLAlchemy, google-genai, pgvector, unittest
- 작업 범위: 누락 Repository·Embedding Service 복구, 단위 테스트, Backend 공통 규칙 감사, 서버 기동 검증
- 제외 범위: 실제 Gemini API 호출, 실제 Neon INSERT, DB Schema 변경, 원본 파일 영구 저장, RAG 검색

## 1. 작업 목적

2026-08-23의 Embedding·VectorDB 저장 작업에서는 기존 추적 파일이 새 기능을 호출하도록 변경됐지만, 새로 작성했어야 할 Python 파일이 Git commit에서 빠졌다.

이 때문에 Uvicorn의 reloader 프로세스는 실행됐지만 실제 FastAPI 애플리케이션을 import하는 자식 프로세스가 다음 오류로 종료됐다.

```text
ModuleNotFoundError: No module named 'app.repositories.document_repository'
```

첫 누락 파일 외에도 `app.services.embedding_service`가 존재하지 않아 하나만 복구하면 다음 import에서 다시 실패할 상태였다.

이번 작업의 목적은 기존 Router·Schema·Frontend 계약을 바꾸지 않고 두 누락 모듈을 복구하고, 같은 문제가 다시 발견되지 않은 채 commit되는 것을 막기 위해 전용 테스트와 실제 애플리케이션 import 검증을 추가하는 것이다.

## 2. 작업 전후 상태

### 작업 전

```text
Frontend 저장 버튼
→ POST /api/admin/ocr/vector-save
→ Admin Router import
→ 존재하지 않는 document_repository import
→ FastAPI 애플리케이션 시작 실패
```

`admin_ocr.py`도 존재하지 않는 `embedding_service.py`와 `document_repository.py`를 참조하고 있었다. 외부 패키지는 정상 설치되어 있었으므로 Python 버전, Uvicorn, PaddleOCR 또는 pip 의존성 문제가 아니었다.

### 작업 후

```text
POST /api/admin/ocr/vector-save
→ Admin Router
→ save_ocr_result_with_embeddings()
→ 완료된 OCR Job 결과 조회
→ EmbeddingService.embed_chunks()
← 1024차원 Vector 목록 반환
→ DocumentRepository.save_with_chunks()
← 저장된 문서 ID와 Chunk 개수 반환
→ OcrVectorSaveResponse 조립
→ Frontend 반환
```

애플리케이션 import와 Uvicorn 기동이 복구됐고, 외부 API와 실제 DB를 사용하지 않는 자동 테스트로 정상·실패 경로를 검증했다.

## 3. 누락 원인

문제가 시작된 commit은 다음 두 개다.

```text
036cced feature:embedding,vectorDB,neonSave
3894a15 fix:embeddingModel교체구조_확립
```

두 commit에는 기존 추적 파일의 수정 상태인 `M`만 포함됐고 새 파일 추가 상태인 `A`가 없었다. `.gitignore`에도 두 Python 파일을 제외하는 규칙은 없었다.

이 형태는 다음 명령을 새 파일이 포함된 작업에서 사용했을 때 발생한다.

```text
git commit -am "..."
```

`-a`는 이미 Git이 추적 중인 수정·삭제 파일만 자동 staging한다. 새 `.py`나 `.md` 같은 untracked 파일은 포함하지 않는다.

## 4. Backend 공통 규칙 준수 감사

검토 기준은 `01_백엔드공통규칙_BACKEND_CODING_GUIDE.md`이며, 실제 복구된 최종 코드를 기준으로 판단했다.

| 점검 항목 | 판정 | 확인 내용 |
|---|---|---|
| 중심 흐름 함수 | 준수 | `save_ocr_result_with_embeddings()`가 Job 조회, Embedding, 검증, DB 저장, Response 조립 순서를 관리한다. |
| 호출 후 중심 함수 복귀 | 준수 | Embedding 결과와 Repository 결과가 모두 중심 함수로 돌아온 뒤 다음 단계가 실행된다. |
| Router 책임 분리 | 준수 | Router는 Request·DB Dependency·Service 호출·HTTP 오류 변환만 담당한다. |
| Service 책임 | 준수 | `admin_ocr.py`가 OCR Vector 저장 기능 전체 순서를 관리한다. |
| Repository 책임 | 준수 | `DocumentRepository`는 문서·Chunk DB 저장과 Transaction 처리에만 집중한다. |
| 외부 AI 모듈 분리 | 준수 | Gemini SDK 호출과 Vector 응답 검증을 `EmbeddingService`에 분리했다. |
| Schema / DTO | 준수 | Request와 Response가 `OcrVectorSaveRequest`, `OcrVectorSaveResponse`로 명시돼 있다. |
| 비동기 사용 | 준수 | 외부 Gemini 네트워크 호출이 있는 Embedding 경계만 `async`로 처리한다. DB Repository는 동기 Session을 사용한다. |
| 로그와 비밀값 | 준수 | 단계·모델·상태만 기록하며 API Key, Chunk 원문, DB 비밀번호를 로그에 남기지 않는다. |
| 기존 구조·수정 범위 | 준수 | 기존 Router→Service→Repository 구조를 유지하고 누락 파일과 테스트만 추가했다. |
| 한국어 설명 | 준수 | 주요 클래스·예외·함수에 한국어 docstring과 필요한 이유를 설명하는 한국어 주석이 있다. |
| 과도한 추상화 방지 | 준수 | Provider용 별도 복잡한 계층을 추가하지 않고 Service 하나와 Repository 하나로 복구했다. |

공통 가이드의 중심 함수 단계 번호 주석은 권장 항목이다. 현재 중심 함수는 호출 순서와 함수명이 명확하고 별도 하위 체인을 만들지 않아 실행 흐름을 위에서 아래로 추적할 수 있다. 따라서 필수 구조 위반은 발견되지 않았다.

## 5. 중심 함수

중심 함수는 다음과 같다.

```text
app.services.admin_ocr.save_ocr_result_with_embeddings()
```

이 함수만 읽으면 전체 순서를 확인할 수 있다.

```text
save_ocr_result_with_embeddings()

→ job_manager.get_job()
← 완료 상태와 기존 OCR Chunk 반환

→ embedder.embed_chunks()
← Chunk 순서를 유지한 Embedding 목록 반환

→ _validate_embeddings_before_storage()
← Chunk 개수와 VECTOR(1024) 계약 검증 완료

→ repository.save_with_chunks()
← document_id와 저장된 Chunk 개수 반환

→ OcrVectorSaveResponse 생성
← Router로 반환
```

Embedding Service와 Repository가 다음 단계를 직접 호출하지 않는다. 각 결과가 항상 중심 함수로 복귀하므로 실행 흐름의 주도권이 `admin_ocr.py`에 유지된다.

## 6. 전체 실행 흐름

```text
사용자가 OCR 분석 실행
→ POST /api/admin/ocr/jobs
→ OCR Job Manager가 OCR·정제·Chunking 수행
→ Frontend가 완료된 jobId와 결과 수신
→ 사용자가 VectorDB 저장 클릭
→ POST /api/admin/ocr/vector-save
→ save_ocr_result_with_embeddings()
→ 메모리에 보관된 완료 Job 확인
→ 기존 Chunk 목록을 Gemini Embedding에 전달
→ 각 Chunk의 1024차원 Vector 검증
→ admin_documents INSERT
→ document ID 확보
→ document_chunks 일괄 INSERT
→ Transaction commit
→ 저장 결과를 Frontend에 반환
```

DB 저장 중 오류가 발생하면 `rollback()`을 실행하여 문서만 저장되고 Chunk 일부가 빠지는 상태를 방지한다.

## 7. 추가 파일과 기존 연결 파일

### 이번 복구에서 추가한 파일

| 파일 | 역할 |
|---|---|
| `backend/app/repositories/document_repository.py` | `admin_documents`와 `document_chunks`를 하나의 Transaction으로 저장한다. |
| `backend/app/services/embedding_service.py` | Gemini batch Embedding 호출, 응답 변환, 입력·Vector 검증, 안전한 Provider 오류 변환을 담당한다. |
| `backend/tests/test_ocr_vector_save.py` | Embedding·Repository·중심 Service의 정상 및 실패 계약을 검증한다. |

### 기존 commit에서 이미 변경돼 있던 연결 파일

| 파일 | 역할 |
|---|---|
| `backend/app/api/admin/router.py` | `/ocr/vector-save` 요청을 받고 중심 Service를 호출한다. |
| `backend/app/services/admin_ocr.py` | OCR Job 조회부터 Response 생성까지 전체 저장 흐름을 관리한다. |
| `backend/app/schemas/admin.py` | `jobId` Request와 저장 결과 Response를 정의한다. |
| `backend/app/core/config.py` | Embedding Provider·Model·Dimension·Timeout 설정을 읽는다. |
| `frontend/src/features/admin/services/apiAdminAiService.ts` | 저장 버튼의 `jobId`를 Backend Endpoint에 전달한다. |
| `frontend/src/features/admin/hooks/useOcrTest.ts` | OCR 결과의 `jobId`를 보관하고 저장 상태를 관리한다. |
| `frontend/src/features/admin/types/ocr.ts` | Frontend Request·Response 타입을 정의한다. |

이번 복구에서는 위 기존 연결 파일을 다시 수정하지 않았다.

## 8. 파일 간 호출 관계

| 순서 | 파일 | 함수 | 역할 |
|---:|---|---|---|
| 1 | `frontend/.../useOcrTest.ts` | `save()` | 완료된 OCR 결과의 `jobId`로 저장 요청을 시작한다. |
| 2 | `frontend/.../apiAdminAiService.ts` | `saveDocument()` | `POST /api/admin/ocr/vector-save`를 호출한다. |
| 3 | `backend/app/api/admin/router.py` | `save_ocr_vector()` | HTTP Request와 DB Session을 받고 중심 Service를 호출한다. |
| 4 | `backend/app/services/admin_ocr.py` | `save_ocr_result_with_embeddings()` | 전체 저장 실행 순서를 관리한다. |
| 5 | `backend/app/services/ocr_job_service.py` | `get_job()` | 완료된 OCR 결과와 기존 Chunk를 반환한다. |
| 6 | `backend/app/services/embedding_service.py` | `embed_chunks()` | Gemini에서 1024차원 Vector 목록을 받아 반환한다. |
| 7 | `backend/app/services/admin_ocr.py` | `_validate_embeddings_before_storage()` | Chunk·Vector 개수와 DB 차원 계약을 확인한다. |
| 8 | `backend/app/repositories/document_repository.py` | `save_with_chunks()` | 문서와 Chunk를 Transaction으로 저장하고 결과를 반환한다. |
| 9 | `backend/app/services/admin_ocr.py` | `save_ocr_result_with_embeddings()` | 저장 결과를 Response Schema로 조립한다. |
| 10 | `backend/app/api/admin/router.py` | `save_ocr_vector()` | HTTP Response를 Frontend로 반환한다. |

## 9. 주요 구현 내용

### 9.1 Embedding 입력 검증

`EmbeddingService.embed_chunks()`는 Provider 호출 전에 다음을 확인한다.

- Chunk 목록이 비어 있지 않은지
- 공백만 있는 Chunk가 없는지
- 설정 차원이 1 이상인지
- 지원하는 Provider가 `gemini`인지
- `GEMINI_API_KEY`가 Backend 설정에 존재하는지

API Key가 없어도 FastAPI 서버 import와 기동은 가능하다. 실제 저장 요청이 들어와 Embedding을 시작할 때만 `EmbeddingUnavailableError`가 발생한다.

### 9.2 Gemini batch Embedding

기존 OCR이 만든 Chunk 목록을 순서대로 한 번의 `embed_content()` 호출에 전달한다.

```text
model: EMBEDDING_MODEL
task_type: RETRIEVAL_DOCUMENT
output_dimensionality: EMBEDDING_DIMENSION
```

응답에서는 다음을 다시 검증한다.

- Chunk 수와 Embedding 수 일치
- 각 Vector가 숫자 목록인지
- 각 Vector가 정확히 1024차원인지
- `NaN`, `Infinity` 같은 유한하지 않은 값이 없는지

### 9.3 안전한 오류 변환

Gemini 오류는 다음 도메인 오류로 변환된다.

| Provider 상태 | Backend 오류 | 의미 |
|---:|---|---|
| Timeout | `EmbeddingGenerationError` | 제한시간 초과 |
| 401 / 403 | `EmbeddingUnavailableError` | API 인증·권한 설정 문제 |
| 404 | `EmbeddingUnavailableError` | 설정한 Embedding 모델을 찾을 수 없음 |
| 429 | `EmbeddingGenerationError` | 할당량 또는 요청 제한 초과 |
| 그 외 | `EmbeddingGenerationError` | 정제된 일반 Provider 오류 |

로그에는 Provider, 모델명, 예외 유형, HTTP 상태만 기록한다. API Key와 Chunk 원문은 기록하지 않는다.

### 9.4 Document Transaction

`DocumentRepository.save_with_chunks()`는 다음 순서로 동작한다.

```text
AdminDocuments 객체 생성
→ db.add()
→ db.flush()로 server default UUID 확보
→ 같은 document_id를 가진 DocumentChunks 목록 생성
→ db.add_all()
→ db.commit()
```

SQLAlchemy 오류가 발생하면 `db.rollback()` 후 `DocumentPersistenceError`를 중심 Service로 반환한다.

## 10. Request / Response

### Request

```http
POST /api/admin/ocr/vector-save
Content-Type: application/json
```

```json
{
  "jobId": "완료된_OCR_Job_ID"
}
```

| 필드 | 설명 |
|---|---|
| `jobId` | Backend 메모리에 보관된 완료 OCR Job을 찾는 ID |

Frontend는 Chunk 본문이나 임의의 Vector를 다시 전송하지 않는다. Backend가 자신이 생성한 OCR Job 결과를 조회해 저장한다.

### Success Response

```json
{
  "message": "OCR 문서와 Chunk를 VectorDB에 저장했습니다.",
  "documentId": "저장된_문서_UUID",
  "chunkCount": 2,
  "embeddingProvider": "gemini",
  "embeddingDimension": 1024,
  "embeddingModel": "설정된_Embedding_모델"
}
```

실제 `message`에는 저장된 Chunk 개수가 포함된다.

### 주요 HTTP 오류

| 상태 | 조건 |
|---:|---|
| 404 | OCR Job이 없거나 TTL 이후 만료됨 |
| 409 | Job이 미완료이거나 저장할 Chunk가 없음 |
| 422 | Chunk·Embedding 개수 또는 1024차원 계약 불일치 |
| 503 | Provider·API Key·모델 설정 문제 |
| 502 | Gemini Timeout·할당량·상위 호출 실패 |
| 500 | Neon Transaction 저장 실패 |

## 11. 실제 기능과 테스트 대역 구분

| 영역 | 현재 코드 | 이번 검증 |
|---|---|---|
| OCR / Chunking | 실제 로컬 처리 | 기존 자동 테스트로 회귀 확인 |
| Embedding | 실제 Gemini SDK 호출 구현 | Fake async client로만 검증, 실호출 안 함 |
| VectorDB 저장 | 실제 SQLAlchemy Session과 Neon 모델 사용 | Mock Session으로 Transaction 계약만 검증, 실제 INSERT 안 함 |
| 원본 파일 URL | `ocr-job://...` 추적 참조값 | 실제 R2/S3 업로드 아님 |
| Frontend 저장 API | 실제 `/ocr/vector-save` HTTP 연결 | production build만 확인, 수동 클릭 안 함 |

따라서 이번 복구는 실제 통합 코드와 자동 테스트를 복원한 작업이다. 실제 Gemini 키의 유효성, 외부 네트워크, 무료 할당량, Neon 권한과 실제 pgvector INSERT 성공까지 확인한 작업은 아니다.

## 12. 추천 코드 읽기 순서

```text
1. backend/app/schemas/admin.py
   Request / Response 계약 확인

2. backend/app/api/admin/router.py
   HTTP 진입점과 오류 매핑 확인

3. backend/app/services/admin_ocr.py
   중심 함수와 전체 저장 순서 확인

4. backend/app/services/embedding_service.py
   외부 Embedding 호출과 Vector 검증 확인

5. backend/app/repositories/document_repository.py
   DB Transaction과 문서·Chunk 관계 확인

6. backend/tests/test_ocr_vector_save.py
   정상·실패 계약 확인

7. frontend/src/features/admin/services/apiAdminAiService.ts
   Frontend와 Backend 연결 확인
```

전체 기능을 이해하려면 `save_ocr_result_with_embeddings()`를 먼저 읽고, 그 함수가 호출하는 Embedding Service와 Repository로 이동하는 순서가 가장 짧다.

## 13. 실행 방법

프로젝트 최상위에서 가상환경과 패키지가 준비돼 있다면 다음 명령으로 Backend와 Frontend를 함께 실행한다.

```powershell
.\run.bat
```

Backend만 실행할 경우:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

확인 주소:

```text
Backend: http://127.0.0.1:8000
Health:  http://127.0.0.1:8000/health
Swagger: http://127.0.0.1:8000/docs
Admin:   http://localhost:5173/admin
```

실제 Vector 저장을 실행하려면 Backend 전용 환경변수 `GEMINI_API_KEY`, `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION`, `EMBEDDING_TIMEOUT_SECONDS`, `DATABASE_URL` 설정이 필요하다. 실제 값은 Git이나 문서에 기록하지 않는다.

## 14. 테스트 및 검증 결과

### 신규 기능 테스트

```powershell
cd backend
.\.venv\Scripts\python.exe -m unittest tests.test_ocr_vector_save -v
```

- 신규 테스트 9개 통과
- Gemini batch 응답 변환
- 빈 Chunk 사전 차단
- API Key 미설정 오류
- 잘못된 Vector 차원 차단
- 429 오류와 비밀값 비노출
- 문서·Chunk 순서 및 관계
- Transaction commit
- DB 오류 rollback
- 중심 Service의 성공 Response
- 1024차원 불일치 시 DB 저장 차단

### Backend 전체 회귀 테스트

```powershell
cd backend
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

- 전체 50개 테스트 통과
- 기존 LLM, Hybrid OCR, Office 직접 추출, OCR Job 테스트 회귀 없음
- Starlette `httpx` 사용 방식에 관한 Deprecation Warning은 있었으나 테스트 실패는 아님

### Import 및 패키지 검증

```powershell
cd backend
.\.venv\Scripts\python.exe -c "import app.main"
.\.venv\Scripts\python.exe -m pip check
```

- `app.main` import 통과
- 누락된 Repository·Embedding Service import 통과
- 손상된 Python 의존성 없음

### Frontend build

```powershell
cd frontend
npm.cmd run build
```

- TypeScript `tsc --noEmit` 통과
- Vite production build 통과
- 1,877개 모듈 변환

### 실제 서버 기동 확인

검증 충돌을 피하기 위해 임시 포트 8011에서 Uvicorn을 실행했다.

```text
Application startup complete
GET /health → HTTP 200
Response → {"status":"ok"}
```

검증 후 임시 Uvicorn 프로세스는 종료했다.

### 실행하지 않은 검증

- 실제 Gemini Embedding API 호출
- 실제 Neon `admin_documents` INSERT
- 실제 Neon `document_chunks`와 `VECTOR(1024)` INSERT
- Frontend 저장 버튼 수동 클릭
- 실제 의료 문서 입력

## 15. 오류 원인과 해결

### 문제

Uvicorn 시작 로그가 출력된 뒤 자식 프로세스가 `ModuleNotFoundError`로 종료됐다.

### 원인

`git commit -am`은 새 untracked 파일을 staging하지 않는다. 기존 Router·Service·Schema·Frontend 변경만 commit되고, 그 코드가 import하던 신규 Repository와 Embedding Service가 Git에 포함되지 않았다.

### 해결

- `document_repository.py` 복구
- `embedding_service.py` 복구
- `test_ocr_vector_save.py` 추가
- `app.main` 직접 import 검증
- Uvicorn 실제 기동과 `/health` 확인
- 신규 및 전체 Backend 테스트 수행

## 16. 현재 구현 상태

| 기능 | 상태 | 설명 |
|---|---|---|
| OCR Job 조회 | 구현 완료 | 완료 Job의 기존 OCR 결과와 Chunk를 사용한다. |
| Gemini Embedding Service | 구현 완료·통합 미검증 | SDK 호출과 오류 처리는 구현됐지만 이번 작업에서 실호출하지 않았다. |
| 1024차원 검증 | 구현 완료 | Service와 중심 저장 경계에서 이중 검증한다. |
| 문서·Chunk Repository | 구현 완료·통합 미검증 | Transaction 코드는 구현됐지만 실제 Neon INSERT는 수행하지 않았다. |
| DB rollback | 자동 테스트 완료 | SQLAlchemy 오류 시 전체 rollback을 확인했다. |
| Frontend API 연결 | 구현 완료 | 기존 commit의 `jobId` 기반 저장 계약을 유지한다. |
| 원본 파일 영구 저장 | 미구현 | `ocr-job://...` 추적 참조값을 사용한다. |
| RAG Vector 검색 | 미구현 | 저장 이후 top-k 검색 Endpoint와 HNSW 인덱스는 별도 작업이다. |
| 관리자 권한 Guard | 미구현 | Admin API 운영 배포 전 인증·권한 보호가 필요하다. |

## 17. 미구현 및 후속 작업

1. 민감하지 않은 테스트 문장으로 Gemini Embedding opt-in smoke test
2. 테스트용 Neon branch에서 문서·Chunk·VECTOR(1024) Transaction 확인
3. 중복 저장 방지를 위한 Job 또는 문서 해시 정책
4. 원본 파일의 비공개 Object Storage 저장 정책
5. OCR Job의 메모리 저장소를 운영용 공유 저장소로 전환
6. 관리자 인증·권한 Guard 적용
7. 배포용 로컬 Embedding Provider 구현
8. 질문 Embedding과 pgvector top-k 검색 구현

배포 환경에서 상용 LLM·Embedding API 키를 사용하지 않는다면 `EmbeddingService.embed_chunks()` 계약은 유지하고, 1024차원 로컬 Embedding 구현체로 교체해야 한다. Frontend Request와 중심 저장 Service는 그대로 유지할 수 있다.

## 18. 작업 시 주의사항

- 실제 Gemini Embedding 호출 시 Chunk 텍스트가 외부 API로 전송된다. 의료·개인정보를 테스트 입력으로 사용하지 않는다.
- `GEMINI_API_KEY`, `DATABASE_URL`과 실제 `.env` 값은 로그·응답·문서·commit에 포함하지 않는다.
- DB의 `document_chunks.embedding`이 `VECTOR(1024)`이므로 Provider 출력 차원을 임의로 변경하지 않는다.
- OCR Job은 현재 프로세스 메모리에 있고 완료 후 TTL이 지나면 만료된다. 서버 재시작 후 이전 `jobId`로 저장할 수 없다.
- `original_file_url`의 `ocr-job://...` 값은 실제 파일 접근 URL이 아니다.
- Repository는 문서와 모든 Chunk를 한 Transaction으로 처리해야 한다. 중간 commit을 추가하지 않는다.
- 현재 Admin Router에는 관리자 권한 Guard가 없으므로 외부에 그대로 노출하지 않는다.

## 19. 새 파일 commit 확인 절차

이번에 추가한 세 파일은 기존에 Git이 추적하지 않던 새 파일이다. 다시 누락되지 않도록 commit 전에 다음 순서로 확인한다.

```powershell
git status --short --untracked-files=all

git add backend/app/repositories/document_repository.py
git add backend/app/services/embedding_service.py
git add backend/tests/test_ocr_vector_save.py
git add docs/2_reports/11_RPT_EmbeddingNeon_누락파일복구_20260824.md

git diff --cached --name-status
git diff --cached --check
git commit -m "fix: 누락된 Embedding 및 Neon 저장 모듈 복구"
git show --name-status --stat HEAD
git status --short --untracked-files=all
```

예상 staging 상태에는 다음 네 개의 `A` 파일이 모두 보여야 한다.

```text
A backend/app/repositories/document_repository.py
A backend/app/services/embedding_service.py
A backend/tests/test_ocr_vector_save.py
A docs/2_reports/11_RPT_EmbeddingNeon_누락파일복구_20260824.md
```

새 파일이 있는 작업에서는 `git commit -am`만 사용하지 않는다.
