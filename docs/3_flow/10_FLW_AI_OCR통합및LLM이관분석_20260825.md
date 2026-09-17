# AI OCR 통합 및 LLM 이관 분석

- 작성일: 2026-08-25
- 분석 기준: `e375712` (`Merge branch 'csj-ocr' into test/admin-merge`)
- 대상 브랜치: `test/admin-merge`
- 문서 목적: 병합 후 공존하는 두 OCR 구현을 하나의 `ai/ocr` 코어로 통합하고, 후속 단계에서 Admin용 LLM 코어도 `ai/llm`으로 옮기기 위한 구조와 이관 순서를 정의한다.
- 이번 문서 범위: 현재 코드 분석과 이관 설계. 실제 코드 이동·삭제·API 변경은 포함하지 않는다.

---

## 1. 결론

현재 OCR은 이름만 다른 동일 구현이 아니라, 서로 다른 계약을 가진 두 개의 독립 파이프라인이다.

1. 서비스 문서 미리보기 경로는 `ai/ocr`의 `run_ocr()`를 직접 호출한다.
2. Admin 경로는 `backend/app/services/hybrid_ocr`의 `process_document()`를 호출한다.

따라서 `hybrid_ocr` 파일을 단순히 `ai/ocr`로 이동하거나 어느 한 구현을 바로 삭제하면 안 된다. 권장 방향은 다음과 같다.

> 문서 형식 판별·검증·추출·이미지 전처리·PaddleOCR 실행·후처리를 `ai/ocr`의 단일 코어로 통합하고, HTTP·인증·FastAPI `UploadFile`·Pydantic 응답·Job·DB 저장은 Backend Adapter에 남긴다.

통합 기준 구현은 기능 범위와 안전장치가 더 많은 `backend/app/services/hybrid_ocr`로 잡는다. 다만 기존 `ai/ocr`의 라인별 결과, 최소 신뢰도 필터, 기울기 보정은 버리지 않고 새 공통 결과 계약에 흡수해야 한다.

OCR이 안정화된 뒤 LLM도 같은 원칙으로 옮긴다.

> Provider 계약·Provider 구현·Model Registry·LLM 실행 코어는 `ai/llm`으로, FastAPI Schema·HTTP 오류 변환·환경 설정 조립은 Backend에 둔다.

---

## 2. 병합 후 현재 상태

Merge의 한쪽에는 기존 서비스용 `ai/ocr`이 있었고, 다른 쪽에는 Admin용 Hybrid OCR과 LLM 계층이 있었다. 병합 결과 두 구현이 모두 보존되었고 실제 호출 지점도 각각 남아 있다.

### 2.1 OCR 경로 A: 서비스 문서 미리보기

```text
DocumentPreviewPanel.tsx
→ frontend/src/api/documents.ts
→ POST /api/documents/ocr
→ backend/app/api/documents/router.py
→ ai.ocr.run_ocr(image_bytes)
→ ai/ocr/pipeline.py
→ ai/ocr/preprocessing.py
→ PaddleOCR
→ ai/ocr/postprocessing.py
→ OcrResponse(text, lines)
```

주요 특성:

- `/api/documents/ocr`은 `get_current_user`를 사용하므로 인증된 사용자 또는 프로젝트의 Chat Token 흐름을 거친다.
- Frontend의 실제 호출 화면은 `/ocr` placeholder 페이지가 아니라 채팅의 `DocumentPreviewPanel`이다.
- 현재 화면에서는 이미지 첨부만 OCR 호출 대상으로 삼는다.
- Backend Endpoint 자체는 이미지 외에 PDF MIME도 허용한다.
- 이미지/PDF 바이트를 `run_ocr()`에 전달하며 PDF는 모든 페이지를 이미지로 렌더링해 OCR한다.
- 반환값에는 전체 Text와 각 OCR Line의 Text·Confidence·Page가 포함된다.
- `run_ocr()`가 동기 CPU 작업인데 Async Router 안에서 직접 실행되므로 처리 중 Event Loop를 막을 수 있다.

### 2.2 OCR 경로 B: Admin 문서 분석

```text
Admin OcrPanel
→ useOcrTest.ts
→ apiAdminAiService.ts
→ POST /api/admin/ocr/jobs
→ OcrJobManager
→ backend/app/services/hybrid_ocr/process_document()
→ 파일 검증
→ PDF / Image / DOCX / PPTX 형식별 추출
→ Text 정제
→ 문자 수 기준 Chunk 생성
→ 메모리 Job 결과 저장
→ GET /api/admin/ocr/jobs/{jobId} Polling
→ Admin 결과 화면
```

선택적으로 다음 저장 흐름이 이어진다.

```text
POST /api/admin/ocr/vector-save
→ admin_ocr.save_ocr_result_with_embeddings()
→ Gemini Embedding
→ DocumentRepository
→ Neon admin_documents + document_chunks 저장
```

주요 특성:

- PDF, PNG, JPG, DOCX, PPTX를 지원한다.
- 확장자·MIME·실제 Binary 구조·파일 크기·PDF 페이지 수·Office 압축 구조를 검증한다.
- 디지털 PDF는 Native Text, 스캔 PDF는 Page OCR, Hybrid PDF는 Text와 Image OCR을 결합한다.
- DOCX/PPTX는 OOXML Text를 직접 추출하고 포함 이미지만 OCR한다.
- PaddleOCR 초기화와 추론에 Lock을 적용한다.
- 진행률 Callback, Job 용량, TTL, 실패 상태를 지원한다.
- 결과는 Admin 전용 `OcrDocumentResponse`이며 라인별 OCR 결과는 제공하지 않는다.
- 현재 `/api/admin/*` Router에는 인증 Dependency가 없다.

### 2.3 두 경로의 실제 차이

| 구분 | `ai/ocr` 서비스 경로 | `backend/services/hybrid_ocr` Admin 경로 | 통합 시 판단 |
|---|---|---|---|
| 중심 함수 | `run_ocr(bytes)` | `process_document(UploadFile, chunk_size, overlap, callback)` | Core 입력을 Framework 독립형으로 새로 정의 |
| 지원 형식 | 이미지, PDF | PNG/JPG, PDF, DOCX, PPTX | Hybrid 지원 범위를 기준으로 통합 |
| PDF | 전 페이지 렌더링 OCR | Native/Scanned/Hybrid 페이지 분기 | Hybrid 방식을 표준으로 채택 |
| Office | 미지원 | 직접 Text 추출 + 포함 Image OCR | 유지 |
| 입력 검증 | Router의 MIME·10MB 검사 | 확장자/MIME/Magic/페이지/압축 안전 검사 | Hybrid 검증을 Core와 Adapter로 분리 |
| 이미지 처리 | OpenCV Resize·Denoise·Deskew | PIL EXIF 회전·투명 배경·Resize·Pixel 제한 | 한 표준 순서로 합치고 Fixture로 회귀 검증 |
| OCR 방향 보정 | Paddle Text Line Orientation 사용 | 사용하지 않음 | 설정값이 아닌 검증된 기본값 하나로 확정 필요 |
| Confidence | Line별 보존, 기본 0.5 미만 Text 제외 | 전체 평균만 계산, Line 필터 없음 | Line 보존 + 집계값을 함께 제공 |
| 읽기 순서 | Paddle 반환 순서 | Box 기준 위→아래·왼쪽→오른쪽 정렬 | Box 정렬 유지 |
| 결과 계약 | `text`, `lines` | 문서 메타, Text, Chunk, Readiness, Notes | 공통 Domain Result와 API Response 분리 |
| Chunking | 없음 | 문자 수 기준 Chunk | OCR Core 밖 `ai/rag` 책임으로 분리 |
| 동시성 | Engine Cache만 있고 Lock 없음 | 초기화/추론 Lock 및 `to_thread` 사용 | Hybrid의 보호 방식 유지 |
| 오류 | 대부분 `ValueError`/일반 Exception | 도메인별 예외 | 공통 OCR 예외 계층 유지 |
| 테스트 | 전용 테스트 없음 | Hybrid/Job/Vector 저장 테스트 존재 | 기존 테스트를 이관 기반으로 사용 |

---

## 3. 문제의 본질

### 3.1 같은 PaddleOCR 모델이 두 번 관리된다

현재 다음 항목이 서로 별도로 구현되어 있다.

- Engine Lazy Loading과 Cache
- Paddle 옵션
- 이미지 변환 타입: OpenCV `ndarray` 대 PIL `Image`
- OCR 결과 Parsing
- Confidence 계산과 필터
- Text 정리
- PDF Rendering Library: `pypdfium2` 대 `PyMuPDF`

한쪽만 버그를 고치거나 Paddle 버전을 올리면 Endpoint별 결과가 달라진다. 같은 파일이 서비스 화면과 Admin 화면에서 서로 다른 Text를 만들 수 있는 구조다.

### 3.2 공통 AI 로직과 Web Application 로직이 결합되어 있다

현재 Hybrid 중심 Service는 다음 Backend 전용 타입과 설정을 직접 참조한다.

- `fastapi.UploadFile`
- `app.core.config.settings`
- `app.schemas.admin.OcrDocumentResponse`

이 상태로 폴더만 `ai/ocr`로 옮기면 `ai` 패키지가 FastAPI App에 역으로 의존한다. 그러면 Local Lab, Batch, Notebook, Worker가 OCR 코어만 독립적으로 재사용하기 어려워진다.

올바른 의존 방향은 다음 하나여야 한다.

```text
Backend / Worker / Local Lab
          ↓
        ai/ocr

ai/ocr ─X→ backend/app
```

### 3.3 OCR과 RAG Chunking의 책임이 섞여 있다

`hybrid_ocr/document_processing_service.py`는 OCR이 끝난 뒤 문자 수 Chunk까지 생성한다. 반면 `ai/rag/chunking.py`에는 임베딩 모델 Tokenizer를 사용하는 별도 Chunker가 있다.

즉 OCR뿐 아니라 Chunking도 두 의미가 공존한다.

- Admin UI 검토용: 사용자가 지정한 문자 수 `chunkSize`, `overlap`
- 실제 RAG용: 임베딩 Tokenizer 기준 `max_tokens`, `overlap_tokens`

둘은 용도가 다르므로 억지로 하나로 합치면 안 된다. 다만 위치와 이름을 명확히 해야 한다.

- OCR Core: 추출된 원문과 정제 Text까지만 책임
- `ai/rag/character_chunking.py`: Admin 미리보기/호환용 문자 Chunk
- `ai/rag/chunking.py`: 실제 검색·Embedding용 Token Chunk
- Backend Workflow: 어떤 Chunk 정책을 사용할지 선택하고 응답 또는 저장 흐름을 조립

### 3.4 원본 Text 보존 계약이 현재 충분하지 않다

`ai/ocr/CLAUDE.md`는 원본 OCR Text와 사용자가 수정한 Text를 분리해 보존하도록 규정한다. 그러나 Hybrid 결과는 정제 전 `ExtractedDocument.text`를 최종 응답에서 버리고 `cleaned_text`만 반환한다.

통합 결과는 최소한 다음을 구분해야 한다.

- `raw_text`: 추출기와 OCR Engine이 합친 원본
- `cleaned_text`: 제어문자·공백을 정리한 Text
- `lines` 또는 `blocks`: Line별 Text, Confidence, Page, 가능하면 Box와 Source
- 사용자 수정본: Backend/DB 계층에서 별도 필드로 보존

---

## 4. 목표 아키텍처

### 4.1 디렉터리 구조

```text
ai/
├─ ocr/
│  ├─ __init__.py
│  ├─ contracts.py              # 입력·결과·Line·Config·Protocol
│  ├─ errors.py                 # Framework 독립 OCR 예외
│  ├─ validation.py             # Bytes, 파일명, MIME, Binary 검증
│  ├─ preprocessing.py          # EXIF, 투명 배경, Resize, Denoise, Deskew
│  ├─ postprocessing.py         # Line 정렬, Confidence, Text 정제
│  ├─ pipeline.py               # 단일 중심 함수 analyze_document()
│  ├─ engines/
│  │  └─ paddle.py              # Lazy Load, Lock, Predict, 결과 변환
│  └─ extractors/
│     ├─ image.py
│     ├─ pdf.py                 # Native/Scanned/Hybrid 분기
│     └─ office.py              # DOCX/PPTX 직접 추출
├─ rag/
│  ├─ chunking.py               # 실제 Token 기준 Chunk
│  └─ character_chunking.py     # Admin 호환 문자 기준 Chunk
└─ llm/                         # OCR 안정화 이후 이관
   ├─ contracts.py
   ├─ application.py
   ├─ registry.py
   └─ providers/
      ├─ ollama.py
      ├─ gemini.py
      └─ mock.py

backend/app/
├─ api/
│  ├─ documents/router.py       # 인증, HTTP 입력/응답, 오류 변환
│  └─ admin/router.py           # 개발판에서만 조건부 Mount
├─ schemas/
│  ├─ document.py
│  └─ admin.py
└─ services/
   ├─ document_ocr.py           # 서비스 API용 Adapter
   ├─ admin_ocr_workflow.py     # Admin 응답·Chunk 조립
   ├─ ocr_job_service.py        # 비동기 Job 상태/TTL/용량
   ├─ admin_ocr.py              # Embedding + Repository 저장 조율
   └─ admin_llm.py              # ai.llm과 Admin Schema 사이 Adapter
```

디렉터리 이름은 구현 시 팀 Naming 기준에 맞춰 조정할 수 있다. 중요한 것은 `ai/ocr`이 `app.*` 또는 FastAPI를 Import하지 않는다는 점이다.

### 4.2 공통 입력과 결과 계약

권장 개념 계약은 다음과 같다.

```python
@dataclass(frozen=True)
class OcrDocumentInput:
    file_name: str
    content_type: str
    content: bytes


@dataclass(frozen=True)
class OcrLine:
    text: str
    confidence: float
    page: int
    box: tuple[float, ...] | None = None
    source: str = "ocr"


@dataclass(frozen=True)
class OcrDocumentResult:
    raw_text: str
    cleaned_text: str
    lines: list[OcrLine]
    page_count: int | None
    document_type: str
    ocr_image_count: int
    average_confidence: float
    warnings: list[str]
```

Core 중심 함수는 다음처럼 Framework와 무관해야 한다.

```python
def analyze_document(
    document: OcrDocumentInput,
    config: OcrConfig,
    progress_callback: ProgressCallback | None = None,
) -> OcrDocumentResult:
    # 1. Binary 문서 검증
    # 2. 파일 형식별 추출
    # 3. Line/Block과 원문 통합
    # 4. 최소 Text 정제
    # 5. 공통 결과 반환
```

Backend는 `UploadFile`을 제한 크기까지만 읽은 후 `OcrDocumentInput`으로 바꾼다. CPU 중심 동기 함수는 `asyncio.to_thread()`로 호출한다.

### 4.3 Endpoint별 Adapter

공통 Core 결과를 Endpoint 계약에 맞게 변환한다.

```text
POST /api/documents/ocr
→ 인증·파일 읽기
→ ai.ocr.analyze_document()
→ text + lines만 OcrResponse로 변환
```

```text
POST /api/admin/ocr/jobs
→ 파일 Byte 복사 및 Job 생성
→ ai.ocr.analyze_document()
→ ai.rag.character_chunking.create_chunks()
→ Admin OcrDocumentResponse로 변환
→ Job 결과 보관
```

이 구조에서는 같은 파일의 OCR 추출 결과는 항상 하나의 Core가 만들고, Endpoint별 차이는 인증·제한·응답 모양·후속 Chunking에만 남는다.

---

## 5. 현재 파일의 이관 위치

| 현재 파일 | 목표 위치/처리 | 이유 |
|---|---|---|
| `ai/ocr/pipeline.py` | 새 `ai/ocr/pipeline.py`에 호환 Wrapper와 중심 함수 구성 | 공개 Import 경로 유지 |
| `ai/ocr/preprocessing.py` | Hybrid 전처리와 통합 | Denoise/Deskew와 EXIF/투명 배경/제한을 모두 보존 |
| `ai/ocr/postprocessing.py` | 공통 Line/Block 후처리로 확장 | Line 결과와 Confidence 보존 |
| `hybrid_ocr/models.py` | `ai/ocr/contracts.py` | Domain 계약이며 Backend 전용이 아님 |
| `hybrid_ocr/errors.py` | `ai/ocr/errors.py` | HTTP 상태와 분리된 Domain 오류 |
| `hybrid_ocr/document_validator.py` | `ai/ocr/validation.py` + Backend Byte Reader | `UploadFile` 의존 제거 필요 |
| `hybrid_ocr/image_preprocessor.py` | `ai/ocr/preprocessing.py` | 중복 전처리 제거 |
| `hybrid_ocr/paddle_ocr_service.py` | `ai/ocr/engines/paddle.py` | 유일한 Paddle 실행 구현으로 사용 |
| `hybrid_ocr/pdf_parser_service.py` | `ai/ocr/extractors/pdf.py` | PDF 추출은 OCR Core 책임 |
| `hybrid_ocr/office_parser_service.py` | `ai/ocr/extractors/office.py` | Office 추출은 OCR Core 책임 |
| `hybrid_ocr/text_cleaner.py` | `ai/ocr/postprocessing.py` 또는 `text_cleaning.py` | 공통 정제 정책 |
| `hybrid_ocr/document_processing_service.py` | `ai/ocr/pipeline.py`와 Backend Adapter로 분해 | Core의 FastAPI·Schema·Settings 의존 제거 |
| `hybrid_ocr/chunk_service.py` | `ai/rag/character_chunking.py` | Chunking은 OCR Engine 책임이 아님 |
| `ocr_job_service.py` | Backend 유지 | 메모리 Task와 API 진행 상태는 Application/Infra 책임 |
| `admin_ocr.py` | Backend 유지 | Job 조회·Embedding·DB Transaction 조율 책임 |
| `embedding_service.py` | OCR 통합 범위에서는 Backend 유지 | 외부 Provider와 저장 Workflow 안정화 후 별도 이관 판단 |
| `api/documents/router.py` | Backend 유지, Core 호출만 교체 | 인증·HTTP Adapter 책임 |
| `api/admin/router.py` | Backend 유지 또는 배포판에서 제외 | HTTP Adapter이며 AI Core가 아님 |

---

## 6. 단계별 이관 계획

### Phase 0. 동작 기준선 고정

코드를 옮기기 전에 두 Endpoint의 현재 결과를 Fixture로 고정한다.

- 가로/세로 회전 JPEG
- 투명 PNG
- 큰 이미지
- 디지털 PDF
- 스캔 PDF
- Text와 Image가 섞인 Hybrid PDF
- Text만 있는 DOCX/PPTX
- 포함 Image가 있는 DOCX/PPTX
- 손상된 파일, 확장자 위장 파일, ZIP Bomb 조건
- Confidence 경계값 위·아래의 OCR Line

이 단계에서 “어느 구현의 결과가 정답인지”가 불명확한 항목을 결정해야 한다.

- Paddle Text Line Orientation 사용 여부
- Denoise/Deskew 기본 적용 여부
- `min_confidence=0.5` 필터 유지 여부
- WebP/BMP/TIFF 지원을 공식화할지 제거할지
- 서비스 API의 10MB와 Admin의 20MB 제한을 Endpoint별로 유지할지 통일할지

### Phase 1. Framework 독립 OCR Core 추출

1. `ai/ocr/contracts.py`, `errors.py`, `validation.py`를 만든다.
2. Hybrid의 PDF/Office/Engine 구현을 `ai/ocr`로 이동한다.
3. 기존 `ai/ocr`의 Line 결과·Confidence 필터·Deskew를 공통 계약에 흡수한다.
4. `ai/ocr`에서 `fastapi`, `app.core`, `app.schemas` Import가 0개인지 검사한다.
5. `analyze_document()` 하나에서 검증→형식별 추출→정제→결과 반환 순서를 읽을 수 있게 한다.

### Phase 2. Admin 경로를 새 Core로 전환

Admin Hybrid 구현이 기능이 더 많으므로 먼저 동일 동작 이관을 검증한다.

1. `admin_ocr_workflow.py`에서 `ai.ocr.analyze_document()`를 호출한다.
2. 문자 Chunker 결과를 기존 `OcrDocumentResponse`로 변환한다.
3. `OcrJobManager`의 Processor 주입 계약은 유지한다.
4. Job Polling 및 Vector Save API 계약을 바꾸지 않는다.
5. 기존 `test_hybrid_ocr.py`, `test_ocr_jobs.py`, `test_ocr_vector_save.py`를 새 Import 경로로 전환해 모두 통과시킨다.

### Phase 3. 서비스 `/documents/ocr` 전환

1. Router의 직접 `run_ocr()` 호출을 Backend Adapter 호출로 바꾼다.
2. OCR Core는 `asyncio.to_thread()`에서 실행해 Event Loop Blocking을 막는다.
3. 새 공통 `lines`를 기존 `OcrLineResponse`로 변환한다.
4. 기존 `ai.ocr.run_ocr()`는 한 Release 동안 호환 Wrapper로 유지할 수 있다.
5. Frontend `extractTextFromImage()` 계약이 유지되는지 확인한다.

### Phase 4. 중복 제거와 배포 정리

두 Endpoint가 새 Core를 사용하는 것이 확인된 뒤에만 다음을 수행한다.

- `backend/app/services/hybrid_ocr` 삭제
- 구 `ai/ocr` 중복 Engine·PDF Rendering 코드 삭제
- `pypdfium2`와 `PyMuPDF` 중 사용하지 않는 의존성 제거
- `backend/requirements.txt`와 `ai/ocr/requirements.txt`의 Paddle 버전 단일화
- Dockerfile에서 새 `ai/ocr` 전체가 포함되는지 확인
- `CLAUDE.md`, README, Flow 문서의 호출 경로 갱신

중복 제거의 완료 조건은 폴더 삭제 자체가 아니라 다음 검색 결과가 하나의 Engine 구현만 가리키는 것이다.

```powershell
rg -n "PaddleOCR|run_ocr|process_document|extract_text" ai backend
```

### Phase 5. Admin 제거와 배포 경계 확정

배포판에서 Admin UI만 제거하는 것은 보안 조치로 충분하지 않다. 현재 Backend는 `app/api/router.py`에서 `admin_router`를 항상 Mount하고, Admin Endpoint 자체에도 인증 Dependency가 없다.

배포판에서는 최소한 다음 둘을 함께 제외해야 한다.

- Frontend `/admin` Route와 Admin Bundle 진입점
- Backend `/api/admin` Router Mount

권장 방식은 `APP_ENV` 또는 명시적인 `ENABLE_ADMIN_API=false` 설정으로 Router Mount 자체를 조건부 처리하는 것이다. 숨겨진 Link나 Frontend Route 삭제만으로는 외부의 직접 HTTP 호출을 막지 못한다.

단, Admin 화면을 제거하더라도 통합된 `ai/ocr` 코어는 `/api/documents/ocr`에서 계속 사용한다. Admin 제거와 OCR Core 삭제를 연결해서는 안 된다.

---

## 7. 호환성과 주요 위험

### 7.1 API Response 손실

Hybrid 결과만 기준으로 통합하면 `/documents/ocr`이 요구하는 Line별 Confidence와 Page 정보가 사라진다. 공통 Domain Result가 Line을 보존하고 Admin Adapter가 필요하지 않은 필드를 숨기는 방향이어야 한다.

### 7.2 OCR 결과 변화

Denoise, Deskew, EXIF 회전, Paddle Orientation, Confidence 필터 중 하나만 달라져도 Text가 변한다. 두 전처리를 무조건 직렬 적용하면 정확도가 오히려 낮아질 수 있으므로 실제 Fixture A/B 결과로 기본 Pipeline을 결정해야 한다.

### 7.3 PDF 비용 증가 또는 정보 손실

모든 PDF 페이지를 OCR하면 느리고 비싸며, Native PDF를 OCR Text로 바꾸면서 표·문단 구조가 손실된다. 반대로 Native Text만 신뢰하면 스캔 페이지와 포함 Image Text가 빠진다. 현재 Hybrid의 페이지별 분기를 표준으로 유지하는 이유다.

### 7.4 Event Loop와 Engine 동시성

PaddleOCR는 CPU/GPU 추론이 무겁고 현재 서비스 경로는 Async Router에서 동기 실행한다. Core는 동기로 유지하되 Backend에서 Thread로 넘기고, 하나의 Engine 인스턴스에는 추론 Lock 또는 제한된 Worker Queue를 적용해야 한다.

### 7.5 메모리 Job의 운영 한계

`OcrJobManager`는 프로세스 메모리에 상태를 둔다. 다중 Worker, 재시작, Scale-out 환경에서는 Job 생성 요청과 Polling 요청이 다른 Instance로 갈 수 있고 재시작 시 상태가 사라진다. OCR 폴더 이동으로 해결되는 문제는 아니다. Admin이 개발판 전용이면 수용 가능하지만, 운영 기능으로 승격할 경우 Redis/DB/Queue 기반 Job으로 별도 전환해야 한다.

### 7.6 Dependency와 Runtime 불일치

현재 `ai/ocr/requirements.txt`는 넓은 Paddle 범위를 허용하고 Backend는 별도로 Paddle 3.3/3.7 계열을 제한한다. 통합 후에는 OCR의 Canonical Dependency 파일을 하나로 만들고 Backend가 그것을 참조해야 한다. PaddleOCR 옵션은 버전별 차이가 있으므로 설치 버전과 테스트 버전을 함께 고정한다.

### 7.7 Docker와 Package 경로

현재 Dockerfile은 `ai/__init__.py`와 `ai/ocr/`를 복사하므로 OCR 목표 구조와는 맞는다. 다만 후속 LLM 이관 뒤에는 `ai/llm/`도 Image에 복사하거나 프로젝트 패키지 자체를 설치하도록 Dockerfile을 바꿔야 한다.

---

## 8. 테스트 전략과 완료 기준

### 8.1 Unit Test

- 파일 형식·MIME·Magic Number 검증
- PDF 페이지 분류: Digital/Scanned/Hybrid
- Office Text와 Image 순서 보존
- EXIF·투명 배경·Resize·Deskew
- OCR Box 읽기 순서
- Line Confidence 필터와 평균값
- Raw/Cleaned Text 분리
- 문자 Chunk와 Token Chunk의 독립 동작
- Engine Lazy Loading, 초기화 Lock, 추론 Lock

### 8.2 Contract Test

- `POST /api/documents/ocr`의 `text`, `lines[]` 형태 유지
- Admin 개발판의 Job 생성→Polling→완료/실패 계약 유지
- Vector Save가 OCR Job의 기존 Chunk 순서와 개수를 그대로 저장
- Domain 오류가 Endpoint별 413/422/500/503 등 기존 HTTP 상태로 변환

### 8.3 Integration Test

- 동일 파일을 서비스 Adapter와 Admin Adapter에 전달했을 때 `raw_text`, `cleaned_text`, Line Confidence가 동일
- Admin Adapter의 차이는 Chunk·Readiness·Notes 추가뿐임을 검증
- 실제 Paddle Smoke Test는 모델 다운로드가 필요한 일반 Test와 분리
- Docker Image 안에서 `from ai.ocr import analyze_document` Import 확인

### 8.4 통합 완료 조건

- OCR Engine 구현이 `ai/ocr`에 하나만 존재한다.
- PDF/Office/Image 추출 구현이 `backend/app/services`에 중복되지 않는다.
- `/documents/ocr`과 Admin 개발판 OCR이 동일 Core를 호출한다.
- `ai/ocr`은 `fastapi`와 `app.*`를 Import하지 않는다.
- 기존 API 계약과 주요 Fixture 결과가 유지된다.
- Raw Text와 Cleaned Text가 구분된다.
- Backend Test와 AI Core Test가 통과한다.
- Backend 요구사항과 Dockerfile이 같은 OCR Dependency를 사용한다.
- 배포판에서는 Frontend Admin Route와 Backend Admin Router가 모두 제외된다.

---

## 9. 후속 LLM 이관 설계

OCR 통합이 끝난 뒤 현재 `backend/app/services/llm`을 `ai/llm`으로 이관한다.

### 9.1 `ai/llm`으로 이동할 항목

- `contracts.py`: Provider 요청·결과·모델 정의·도메인 예외
- `application.py`: 모델 조회와 실행 순서
- `registry.py`: Model/Provider Registry
- `providers/ollama.py`
- `providers/gemini.py`
- `providers/mock.py` 또는 개발 전용 Fixture 위치

### 9.2 Backend에 남길 항목

- `app/schemas/admin.py`의 Request/Response Schema
- `app/api/admin/router.py`의 HTTP 처리
- `app/services/admin_llm.py`의 Schema Adapter
- `app/core/config.py`의 환경 변수 읽기

다만 `ai/llm`이 `app.core.config.Settings`를 직접 받으면 안 된다. Backend가 환경 변수를 읽어 Framework 독립 Config 또는 생성자 인자로 주입해야 한다.

```text
Backend Settings
→ ProviderConfig 생성
→ ai.llm Registry/Application 조립
→ Admin Schema로 결과 변환
```

### 9.3 LLM 이관 전 선행 결정

- `mock` Provider를 제품 AI Core에 둘지 Test Fixture로 옮길지
- Admin 제거 후 실제 LLM Core의 운영 호출자가 무엇인지
- Ollama/Gemini Model Registry를 코드 상수로 둘지 설정 파일로 분리할지
- 의료 Text를 외부 Gemini로 전송할 때의 개인정보·동의·로그 정책
- Docker Image에 `ai/llm`을 포함할지 LLM Worker를 별도 배포할지

Admin 화면이 최종 배포에서 제거되고 다른 LLM 호출자가 아직 없다면, 폴더 이동부터 하기보다 먼저 실제 운영 Use Case와 공통 입력/결과 계약을 정의하는 편이 안전하다.

---

## 10. 권장 작업 순서 요약

```text
1. OCR Golden Fixture와 API Contract 고정
2. Hybrid 기능을 Framework 독립 ai/ocr Core로 추출
3. 기존 ai/ocr의 Line·Confidence·Deskew 장점 흡수
4. Admin OCR을 새 Core로 전환하고 회귀 테스트
5. /documents/ocr을 새 Core로 전환하고 비동기 Blocking 해소
6. 중복 hybrid_ocr와 구 Engine 제거
7. Dependency·Docker·문서 정리
8. 배포판에서 Frontend Admin + Backend Admin Router 동시 제외
9. OCR 안정화 후 같은 원칙으로 backend/services/llm → ai/llm 이관
```

최우선 원칙은 **폴더를 먼저 옮기는 것이 아니라 공통 Domain 계약과 단일 중심 함수를 먼저 만드는 것**이다. 이 순서를 따르면 현재 두 Endpoint의 장점을 보존하면서도, 이후 Worker·Local Lab·RAG·LLM에서 `ai` 패키지를 독립적으로 재사용할 수 있다.
