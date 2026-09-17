# Admin FastAPI Mock Backend 및 Frontend 연동

- 작업일: 2026-08-18
- Backend API Prefix: `/api/admin`
- Frontend 화면: `/admin`
- 구현 범위: OCR·Vector 저장·LLM 비교 Mock API와 React HTTP 연결
- 제외 범위: 실제 파일 업로드, OCR 엔진, LLM/Ollama, Embedding, RAG, VectorDB 저장

## 1. 작업 목적

React Admin 화면이 브라우저 내부 fixture 대신 FastAPI Backend와 실제 HTTP 통신하도록 연결했다. Backend는 현재 고정 Mock 결과를 반환하지만 Router, Pydantic Schema, 중심 Service 함수와 Mock 교체 위치를 분리해 향후 실제 OCR·LLM 구현으로 교체할 수 있도록 구성했다.

```text
React Admin
→ apiAdminAiService
→ 공통 apiClient
→ FastAPI Admin Router
→ Admin Service 중심 함수
→ Backend Mock 생성
→ Pydantic Response
→ React 결과 화면
```

## 2. 기존 구조 분석 결과

- FastAPI 진입점은 `backend/app/main.py`의 `app = create_app()`이다.
- 통합 Router는 `backend/app/api/router.py`에서 기본 `/api` prefix 아래 등록된다.
- Admin Router는 이미 `/admin` prefix로 등록되어 있었으나 endpoint는 비어 있었다.
- 기존 Backend는 Router → Service → Repository 패턴을 사용한다.
- 이번 Mock 기능은 DB가 필요하지 않아 Repository를 추가하지 않았다.
- CORS 기본 허용 origin은 `http://localhost:5173`이다.
- Frontend 공통 `apiClient`의 기본 주소는 `http://localhost:8000/api`다.

## 3. Backend 생성·수정 파일

### 생성

| 파일 | 역할 |
|---|---|
| `backend/app/schemas/admin.py` | OCR·저장·LLM 요청/응답 Pydantic 계약 |
| `backend/app/services/admin_ocr.py` | OCR 검증, Mock 생성, 응답 조립 중심 흐름 |
| `backend/app/services/admin_llm.py` | 모델 검증, 모델별 Mock 생성, 응답 조립 중심 흐름 |

### 수정

| 파일 | 변경 이유 |
|---|---|
| `backend/app/api/admin/router.py` | 3개 Admin endpoint를 기존 `/api/admin` Router에 연결 |

`main.py`, 공통 Router 등록, DB, 인증, 기존 서비스는 수정하지 않았다.

## 4. Frontend 생성·수정 파일

### 생성

| 파일 | 역할 |
|---|---|
| `frontend/src/features/admin/services/apiAdminAiService.ts` | Admin 요청을 FastAPI JSON 계약으로 변환하는 HTTP service |

### 수정

| 파일 | 변경 이유 |
|---|---|
| `frontend/src/features/admin/services/adminAiService.ts` | 실행 binding을 `mockAdminAiService`에서 `apiAdminAiService`로 교체 |

기존 `mockAdminAiService.ts`와 fixture는 개발 참고 및 필요 시 독립 UI 테스트에 사용할 수 있도록 보존했다. 현재 실제 화면은 이 Mock service를 호출하지 않는다.

## 5. API 목록

| Method | URL | Request | Response | 목적 |
|---|---|---|---|---|
| POST | `/api/admin/ocr/analyze` | `OcrAnalyzeRequest` | `OcrDocumentResponse` | 파일 메타데이터 기반 OCR Mock |
| POST | `/api/admin/ocr/vector-save-test` | `VectorSaveTestRequest` | `VectorSaveTestResponse` | DB Side Effect 없는 저장 Mock |
| POST | `/api/admin/llm/compare` | `LlmCompareRequest` | `list[LlmModelResponse]` | 다중 모델 응답 비교 Mock |

## 6. OCR API 흐름

```text
OcrPanel
→ useOcrTest.analyze()
→ apiAdminAiService.analyzeDocument()
→ POST /api/admin/ocr/analyze
→ Router.analyze_ocr()
→ admin_ocr.analyze_document()       # 중심 함수
→ validate_ocr_request()
→ create_mock_ocr_result()           # 실제 OCR 교체 위치
→ build_ocr_response()
→ OcrDocumentResponse
→ OcrResultSummary
```

파일 본문은 전송하지 않는다. Frontend `File`에서 아래 메타데이터만 JSON으로 전달한다.

```json
{
  "documentName": "sample.pdf",
  "fileSize": 4096,
  "contentType": "application/pdf",
  "chunkSize": 512,
  "overlap": 50
}
```

응답 예시:

```json
{
  "documentName": "sample.pdf",
  "pageCount": 4,
  "characterCount": 4286,
  "estimatedChunks": 11,
  "confidence": 94.8,
  "extractedText": "환자의 현재 증상과 과거 병력을 함께 검토해야 합니다.",
  "chunks": ["[Chunk 01] ...", "[Chunk 02] ..."],
  "readiness": "review",
  "notes": ["표가 포함된 페이지는 열 순서를 확인해 주세요."]
}
```

## 7. VectorDB 저장 테스트 흐름

```text
OcrResultSummary
→ useOcrTest.save()
→ POST /api/admin/ocr/vector-save-test
→ admin_ocr.save_document_test()
→ 실제 DB 저장 없이 Mock 완료 메시지 반환
```

Request:

```json
{ "documentName": "sample.pdf" }
```

Response:

```json
{
  "message": "저장 테스트가 완료되었습니다. 실제 VectorDB에는 저장되지 않았습니다."
}
```

## 8. LLM API 흐름

```text
LlmPanel
→ useLlmComparison.compare()
→ apiAdminAiService.compareModels()
→ POST /api/admin/llm/compare
→ Router.compare_llm()
→ admin_llm.compare_models()         # 중심 함수
→ validate_llm_request()
→ create_mock_model_results()        # 실제 LLM 교체 위치
→ build_compare_response()
→ list[LlmModelResponse]
→ LlmResultGrid
```

Request 예시:

```json
{
  "prompt": "문서의 핵심 내용을 요약해 주세요.",
  "modelIds": ["medgemma", "qwen", "llama"],
  "documentName": "reference.pdf",
  "chunkSize": 512,
  "overlap": 50
}
```

Response 예시:

```json
[
  {
    "modelId": "medgemma",
    "status": "success",
    "answer": "의료 정보의 한계를 밝히고 위험 신호가 있다면 전문가 평가를 안내합니다.",
    "error": null,
    "responseTimeSeconds": 6.42,
    "inputTokens": 64,
    "outputTokens": 186,
    "chunkSize": 512,
    "overlap": 50
  },
  {
    "modelId": "llama",
    "status": "error",
    "answer": null,
    "error": "Mock provider가 일시적으로 응답하지 않았습니다.",
    "responseTimeSeconds": 8.74,
    "inputTokens": 0,
    "outputTokens": 0,
    "chunkSize": 512,
    "overlap": 50
  }
]
```

Llama 오류는 Frontend의 부분 오류 카드 흐름을 검증하기 위한 의도적인 Backend Mock fixture다.

## 9. Schema와 Validation

- Frontend의 camelCase JSON과 Backend의 snake_case Python 속성을 alias로 연결한다.
- OCR 허용 확장자: `.pdf`, `.png`, `.jpg`, `.jpeg`
- 비교 모델: `medgemma`, `gemma`, `qwen`, `llama`
- 모델은 2~4개이며 중복 ID를 허용하지 않는다.
- `Chunk Size`: 100~4096
- `Overlap`: 0 이상이며 Chunk Size보다 작아야 한다.
- 공백만 있는 Prompt, 지원하지 않는 파일/모델은 HTTP 422를 반환한다.

## 10. Mock 교체 위치

### 실제 OCR

```text
backend/app/services/admin_ocr.py
create_mock_ocr_result()
→ 실제 OCR engine 호출 함수로 교체
```

`analyze_document()`의 검증 및 Response 조립 순서는 유지한다.

### 실제 LLM

```text
backend/app/services/admin_llm.py
create_mock_model_results()
→ 실제 Ollama/LLM 다중 호출 함수로 교체
```

`compare_models()`의 검증 및 Response 조립 순서는 유지한다.

### 실제 VectorDB

```text
backend/app/services/admin_ocr.py
save_document_test()
→ Repository 또는 Vector 저장 service 호출 추가
```

Side Effect가 추가되면 중심 함수에서 호출 위치가 보이도록 유지한다.

## 11. 실행 방법

Backend:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Frontend:

```powershell
cd frontend
npm.cmd run dev
```

확인 주소:

- Admin UI: `http://localhost:5173/admin`
- FastAPI 문서: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

`VITE_API_URL`을 설정하지 않으면 Frontend는 `http://localhost:8000/api`를 사용한다.

## 12. 검증 결과

- Frontend `npm.cmd run build`: 통과
  - TypeScript `tsc --noEmit`: 통과
  - Vite production build: 통과
- Backend `python -m compileall -q app`: 통과
- Vite `/admin`: HTTP 200
- FastAPI `/health`: `status=ok`
- localhost:5173 CORS preflight: HTTP 200, allow-origin 정상
- OCR API: PDF Mock 결과와 chunk 응답 정상
- Vector 저장 API: 실제 미저장 안내 응답 정상
- LLM API: 3개 결과 및 `success, success, error` 부분 오류 정상
- production bundle에 Admin API endpoint 포함 확인
- 연결 가능한 Browser 인스턴스가 없어 자동 화면 interaction 검증은 수행하지 못함

## 13. 기존 코드 영향과 미구현 항목

Admin service binding 외 다른 Frontend 기능은 변경하지 않았다. Backend는 기존 빈 Admin Router에 endpoint를 추가했으며 인증, 사용자 API, DB Schema와 migration에는 영향을 주지 않았다.

현재 구현하지 않은 항목:

- 파일 본문 업로드 및 저장
- 실제 OCR 엔진
- 실제 Gemma/Qwen/MedGemma/Llama 호출
- Ollama
- Chunking과 Embedding
- RAG 검색
- VectorDB 영속화
- Admin 인증/권한 guard
