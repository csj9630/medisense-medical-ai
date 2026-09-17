# Admin OCR 웹 URL 수집 확장 구현 지시서

- 작성일: 2026-08-31
- 작업 영역: Frontend / Backend / AI OCR Core / Embedding / Neon
- 대상 기능: 관리자 OCR 탭의 웹페이지 URL 입력·미리보기·본문 추출·내부 이미지 OCR·Chunk·Vector 저장
- 주요 기술: React 19, TypeScript, FastAPI, Pydantic, HTTP Client, lxml, PaddleOCR, Gemini Embedding, PostgreSQL, pgvector
- 문서 성격: 현재 코드 분석을 바탕으로 한 후속 구현 지시서
- 구현 범위: OCR 탭의 파일/웹페이지 URL 입력 전환, 단일 공개 웹페이지 수집, 정적 HTML 본문 추출, 제한된 내부 이미지 OCR, 기존 Admin OCR Job·Gemini·Neon 저장 흐름 재사용
- 고정 영역: `GeminiEmbeddingService`, `document_chunks.embedding VECTOR(1024)`, `/ocr/vector-save`, 기존 Embedding 검증·Transaction
- 1차 제외 범위: 임베딩 모델 선정·교체, `chunk_embeddings`/RAG 수집 연결, Vector Schema 변경, 전체 사이트 크롤링, 로그인 페이지, JavaScript 렌더링 전용 페이지, 동영상·SVG OCR, 예약 수집, URL 변경 감지

---

## 1. 분석 결론

이 기능은 웹페이지 전용 OCR·Chunk·Embedding 파이프라인을 별도로 복제하면 안 된다.

권장 구조는 다음과 같다.

```text
파일 입력
→ 기존 POST /api/admin/ocr/jobs
→ 기존 파일 OCR Workflow
┐
├→ 공통 OcrDocumentResponse
│ → 기존 Job 상태 조회
│ → 기존 추출 Text/Chunk 화면
│ → 기존 POST /api/admin/ocr/vector-save
│ → Gemini Embedding
│ → Neon 저장
┘

웹 URL 입력
→ 신규 POST /api/admin/ocr/url-jobs
→ 신규 Web OCR Workflow
   → URL 보안 검증
   → HTML 다운로드
   → 본문 구조 추출
   → 내부 이미지 제한 다운로드
   → 기존 PaddleOCR 전처리·Engine 재사용
   → 공통 OcrDocumentResponse
→ 이후 기존 흐름에 합류
```

즉 새로 구현할 핵심은 **웹 입력 Adapter와 웹 콘텐츠 추출 단계**다. 다음 기능은 기존 구현을 그대로 재사용한다.

- OCR Job 생성 후 Polling하는 화면 흐름
- 관리자용 문자 수 기준 Chunk 생성
- 추출 Text와 Chunk 표시
- 완료 Job을 기준으로 한 저장 요청
- Gemini 1024차원 Embedding
- `admin_documents`와 `document_chunks` Transaction 저장

기존 파일 API 계약은 유지하고 URL 전용 JSON Endpoint를 추가하는 방식을 권장한다. 하나의 Endpoint에서 `multipart/form-data`와 JSON을 동시에 처리하려고 하면 Router와 Frontend Adapter가 불필요하게 복잡해지고 기존 파일 업로드 회귀 위험이 커진다.

### 1.1 이번 작업의 범위 고정

임베딩 모델은 팀 협의가 끝나지 않았으므로 이번 작업에서 변경하지 않는다.

```text
이번 작업에서 유지
→ EMBEDDING_PROVIDER=gemini
→ gemini-embedding-001
→ 1024차원
→ vector_db.document_chunks.embedding
→ 기존 save_ocr_result_with_embeddings()
→ 기존 DocumentRepository.save_with_chunks()

이번 작업에서 제외
→ RAG_EMBEDDING_PROVIDER 선정
→ Sentence-Transformers 모델 연결
→ hashing-placeholder 사용
→ document_ingestion_service.ingest_document() 연결
→ vector_db.chunk_embeddings 저장
→ 기존 Gemini Vector 마이그레이션
→ Embedding/Vector Schema 리팩터링
```

웹 URL은 파일과 다른 **입력·추출 경로**만 추가하고, `OcrDocumentResponse`를 만든 뒤부터는 기존 파일 OCR과 같은 Chunk·Gemini·Neon 저장 경로로 합류시킨다. 임베딩 구조의 문제를 URL 기능 구현 중 함께 해결하려고 하지 않는다.

---

## 2. 현재 구현 상태

### 2.1 Frontend

현재 관리자 OCR 화면은 파일만 입력할 수 있다.

```text
AdminPage
→ OcrPanel
→ OcrDropzone
→ useOcrTest.selectFile()
→ useOcrTest.analyze()
→ apiAdminAiService.analyzeDocument()
→ POST /api/admin/ocr/jobs (multipart/form-data)
→ GET /api/admin/ocr/jobs/{jobId} 반복 조회
→ OcrResultSummary
→ POST /api/admin/ocr/vector-save
```

주요 제약은 다음과 같다.

- `useOcrTest.ts`가 입력을 `File | null` 하나로만 보관한다.
- `AnalyzeDocumentRequest`에는 `file`만 존재한다.
- `OcrDropzone.tsx`는 PDF, PNG, JPG, DOCX, PPTX만 선택한다.
- `OcrFilePreview.tsx`는 브라우저 Object URL 기반 파일 미리보기만 담당한다.
- `OcrResultSummary.tsx`는 파일 확장자로 페이지/슬라이드 단위를 판단한다.

### 2.2 Backend HTTP와 Job

현재 실제 Admin 화면은 동기 `/ocr/analyze`가 아니라 Job API를 사용한다.

```text
POST /api/admin/ocr/jobs
→ OcrJobManager.create_job()
→ 메모리 Job 등록
→ asyncio Task
→ OcrWorkflowService.process_document()
→ GET /api/admin/ocr/jobs/{jobId}
```

`OcrJobManager`는 파일 byte, 파일명, MIME을 복사한 뒤 `UploadFile`을 다시 만들어 파일 Processor에 전달한다. Processor 계약 자체가 파일 전용이므로 URL 작업을 추가하려면 입력 종류를 구분하는 공개 메서드와 내부 실행 함수가 필요하다.

Job은 단일 FastAPI 프로세스 메모리에 있고 기본 TTL은 60분이다. Backend 재시작, 다중 Worker, Scale-out 환경에서는 Job 유실 또는 Polling Instance 불일치가 생길 수 있다. 이번 URL 확장만으로 이 문제를 해결하지 말고 기존 운영 제약으로 유지한다.

### 2.3 OCR Core

`ai/ocr/pipeline.py`의 중심 함수는 byte 문서를 대상으로 한다.

```text
analyze_document()
→ validate_document()
→ Image/PDF/Office 형식별 추출
→ clean_document_text()
→ OcrDocumentResult
```

현재 파일 검증기는 확장자와 Binary 구조를 기준으로 PDF, PNG, JPG, DOCX, PPTX만 허용한다. URL이나 HTML을 가짜 파일로 만들어 이 함수에 통과시키지 않는다. 웹페이지는 네트워크 수집과 SSRF 방어가 필요한 별도 입력 종류이기 때문이다.

단, 다음 OCR 자산은 웹 이미지 처리에서 반드시 재사용한다.

- `ai/ocr/preprocessing.py`의 이미지 크기·픽셀·투명도·방향 전처리
- `ai/ocr/engine.py`의 PaddleOCR 지연 로딩 Engine
- `ai/ocr/postprocessing.py`의 Text 정제
- `ai/ocr/contracts.py`의 `OcrLine`, `OcrDocumentResult`, `ProgressCallback`

### 2.4 Chunk와 Vector 저장

현재 저장 흐름은 다음과 같다.

```text
POST /api/admin/ocr/vector-save { jobId }
→ save_ocr_result_with_embeddings()
→ 완료 Job의 기존 chunks 조회
→ Gemini Embedding(RETRIEVAL_DOCUMENT, 1024차원)
→ DocumentRepository.save_with_chunks()
→ vector_db.admin_documents
→ vector_db.document_chunks.embedding VECTOR(1024)
```

웹 URL도 `OcrDocumentResponse.chunks`를 만들 수 있으면 이 저장 흐름을 그대로 사용할 수 있다. Frontend가 추출 Text나 Chunk를 다시 저장 API로 전송하지 않게 한다. 저장의 신뢰 기준은 계속 Backend Job이어야 한다.

### 2.5 반드시 구분할 현재 RAG 제약

Admin OCR 저장과 실제 상담 RAG 검색은 현재 서로 다른 Embedding 경로를 사용한다.

```text
Admin OCR 저장
→ document_chunks.embedding
→ Gemini 1024차원

상담 RAG 검색
→ chunk_embeddings
→ provider_name별 Embedding
→ rag_search_service.search()
```

따라서 이 지시서에서 말하는 “기존 OCR처럼 Embedding 저장”은 **현재 Admin OCR과 같은 Gemini/`document_chunks.embedding` 저장**을 뜻한다. 이번 범위에서는 `document_ingestion_service.ingest_document()`를 호출하거나 `chunk_embeddings`에 추가 저장하지 않는다. 저장 직후 상담 RAG 검색 대상이 되는 통합은 임베딩 모델 협의 후 별도 작업으로 진행한다. 이 차이를 숨긴 채 URL 기능이 RAG 검색까지 완성됐다고 보고하면 안 된다.

---

## 3. 1차 구현 목표와 완료 기준

### 3.1 지원 입력

- 사용자가 `http://` 또는 `https://` 단일 URL을 입력한다.
- 파일 입력과 URL 입력은 동시에 활성화하지 않는다.
- Admin의 상위 탭을 `파일 OCR`, `웹 OCR`로 다시 나누지 않고 기존 OCR 탭 안에서 입력 방식만 전환한다.
- 화면 문구에서는 URL을 파일처럼 취급하는 `URL 업로드` 대신 `웹페이지 URL`, `웹페이지 가져오기`, `웹페이지 가져와 분석`을 사용한다.
- 공개적으로 접근 가능한 정적 HTML 페이지를 대상으로 한다.
- 한 URL에서 연결된 다른 문서 페이지로 이동하거나 사이트 전체를 순회하지 않는다.
- HTML에 포함된 제한된 수의 Raster Image만 추가 다운로드해 OCR한다.

### 3.2 사용자에게 보여줄 결과

- 입력 URL의 미리보기 또는 미리보기 불가 안내와 새 탭 링크
- 최종 이동 URL과 페이지 제목
- 정제된 본문과 이미지 OCR Text를 합친 전체 추출 Text
- 추출 문자 수, OCR 이미지 수, 품질 경고
- 사용자가 지정한 `chunkSize`와 `overlap` 기준 Chunk 목록
- 기존과 같은 VectorDB 저장 버튼과 저장 결과

### 3.3 완료 조건

- 파일 업로드 OCR이 기존과 동일하게 동작한다.
- URL Job 생성 후 기존 Job 조회 Endpoint로 진행률과 결과를 받을 수 있다.
- HTML 본문의 `script`, `style`, `nav`, `footer`, form 요소가 추출 Text에 섞이지 않는다.
- 상대 이미지 URL이 최종 페이지 URL 기준 절대 URL로 변환된다.
- 허용된 이미지에만 기존 PaddleOCR가 실행된다.
- URL Job 결과의 Chunk를 Frontend가 재전송하지 않고 기존 저장 API가 읽는다.
- DB의 `original_file_url`에는 `ocr-job://...` 대신 검증된 최종 HTTP(S) URL이 저장된다.
- 파일과 URL 모두 기존 Gemini 1024차원 Embedding과 `document_chunks.embedding` 저장 계약을 사용한다.
- `chunk_embeddings`, RAG Provider, Embedding 모델 설정과 Vector Schema에는 변경이 없다.
- 내부망·localhost·메타데이터 IP를 대상으로 한 서버 요청이 차단된다.
- URL Job Endpoint는 Backend의 관리자 권한 검사를 통과한 사용자만 호출할 수 있다.
- 정적 HTML 기준 테스트와 Frontend TypeScript Build가 통과한다.

---

## 4. 목표 디렉터리와 책임

권장 추가·수정 구조는 다음과 같다.

```text
frontend/src/features/admin/
├─ components/ocr/
│  ├─ OcrPanel.tsx                 # 파일/URL 입력 모드 조립
│  ├─ OcrSourceSelector.tsx        # 신규: 입력 종류 선택
│  ├─ OcrUrlInput.tsx              # 신규: URL 입력·형식 오류 표시
│  ├─ OcrWebPreview.tsx            # 신규: 제한된 미리보기와 새 탭 링크
│  ├─ OcrDropzone.tsx              # 기존 파일 입력 유지
│  ├─ OcrFilePreview.tsx           # 기존 파일 미리보기 유지
│  └─ OcrResultSummary.tsx         # 웹 Source 표시 보완
├─ hooks/useOcrTest.ts             # File/URL Discriminated State와 실행 분기
├─ services/apiAdminAiService.ts   # URL Job JSON 요청 추가
├─ services/adminAiService.ts      # URL 분석 계약 추가
├─ types/ocr.ts                    # Source/Request/Response 타입 확장
└─ admin.css                       # URL 입력·모드·Preview 스타일

backend/app/
├─ api/admin/router.py             # POST /ocr/url-jobs 추가
├─ schemas/admin.py                # OcrUrlJobRequest, Source Meta 추가
├─ core/config.py                  # 웹 수집 한도 설정
├─ services/
│  ├─ ocr_job_service.py           # 파일/URL Job 실행 분기
│  ├─ ocr_workflow.py              # 파일 Workflow 유지, 공통 응답 Builder 재사용
│  ├─ web_ocr_workflow.py          # 신규: 웹 전체 중심 흐름
│  ├─ web_document_fetcher.py      # 신규: URL 검증·Redirect·HTML/Image 다운로드
│  └─ admin_ocr.py                 # 저장 Source Reference 분기
└─ tests/
   ├─ test_admin_ocr_api.py
   ├─ test_ocr_jobs.py
   ├─ test_web_document_fetcher.py # 신규
   ├─ test_web_ocr_workflow.py     # 신규
   └─ test_ocr_vector_save.py

ai/ocr/
├─ contracts.py                    # Web 입력/중간 결과 계약 또는 별도 web_contracts.py
├─ extractors/web.py               # 신규: HTML 구조 추출, Image 후보, OCR Text 병합
├─ postprocessing.py               # 기존 정제 재사용
├─ preprocessing.py                # 기존 이미지 전처리 재사용
└─ engine.py                       # 기존 Paddle Engine 재사용

tests/ai/ocr/
└─ test_web_extractor.py           # 신규: 네트워크 없는 HTML 추출 단위 테스트
```

`ai/ocr/extractors/web.py`에는 HTTP Client, FastAPI, Pydantic, Backend Settings를 Import하지 않는다. Network I/O와 SSRF 방어는 Backend의 `web_document_fetcher.py`, HTML 분석과 OCR 결과 결합은 Framework 독립 AI 계층의 책임으로 나눈다.

---

## 5. 중심 함수

### 5.1 웹 처리 중심 함수

신규 중심 함수는 `WebOcrWorkflowService.process_url()`로 둔다.

```python
async def process_url(
    self,
    url: str,
    chunk_size: int,
    overlap: int,
    progress_callback: ProgressCallback | None = None,
) -> OcrDocumentResponse:
    # 1. Chunk 옵션과 URL 문법을 검증한다.
    # 2. SSRF 검사를 통과한 URL의 HTML을 제한 크기로 받는다.
    # 3. HTML에서 제목, 본문 구조, Image 후보를 추출한다.
    # 4. 허용 개수·크기 내 Image를 안전하게 받는다.
    # 5. 기존 Paddle 전처리·Engine으로 Image OCR을 실행한다.
    # 6. 본문과 Image OCR 결과를 순서가 드러나는 Text로 합친다.
    # 7. 기존 Text 정제와 Admin 문자 Chunk를 실행한다.
    # 8. 기존 OcrDocumentResponse 계약으로 반환한다.
```

호출과 복귀 관계는 다음처럼 유지한다.

```text
process_url()
→ validate_chunk_options()
← 검증 완료

→ WebDocumentFetcher.fetch_page()
← final_url + HTML + Content-Type

→ parse_web_document()
← title + 본문 Block + Image 후보

→ WebDocumentFetcher.fetch_images()
← 제한을 통과한 Image byte

→ process_web_document()
← OcrDocumentResult

→ create_chunks()
← 기존 문자 Chunk

→ build_admin_ocr_response()
← OcrDocumentResponse
```

한 함수가 네트워크, DOM 분석, OCR, Chunk, DB 저장까지 모두 직접 구현하지 않는다. 반대로 각 세부 함수가 다음 단계를 자동 호출하지도 않는다. 전체 실행 순서는 `process_url()`에서 확인할 수 있어야 한다.

### 5.2 저장 중심 함수

저장은 계속 다음 함수를 중심으로 한다.

```text
save_ocr_result_with_embeddings()
```

이 함수는 입력 종류와 관계없이 다음만 수행한다.

```text
완료 Job 확인
→ Job Chunk Embedding
→ Vector 개수·차원 검증
→ Source Reference 결정
→ Repository Transaction 저장
→ 저장 Response 반환
```

URL 수집 중 DB를 저장하거나 Embedding을 생성하지 않는다. 사용자가 결과를 검토한 뒤 저장 버튼을 눌렀을 때만 기존 저장 흐름을 실행한다.

---

## 6. Frontend 수정 지시

### 6.1 입력 상태를 Discriminated Union으로 변경

`file`과 `url`을 독립 State로 흩어 놓기보다 하나의 Source 상태로 관리한다.

```typescript
type OcrSource =
  | { type: 'file'; file: File }
  | { type: 'url'; url: string }
  | null;
```

분석 요청도 같은 방식으로 구분한다.

```typescript
type AnalyzeOcrRequest =
  | {
      sourceType: 'file';
      file: File;
      chunkSize: number;
      overlap: number;
      signal?: AbortSignal;
    }
  | {
      sourceType: 'url';
      url: string;
      chunkSize: number;
      overlap: number;
      signal?: AbortSignal;
    };
```

입력 모드를 바꿀 때 다음 상태를 함께 초기화한다.

- 이전 Source
- 분석 결과
- 분석 오류
- 저장 상태와 메시지
- 진행률
- 진행 중 `AbortController`

### 6.2 입력 방식 분리 원칙과 OcrPanel

파일과 URL은 **입력 방식만 다르고 분석 이후의 검토·Chunk·Embedding·저장 목적은 같다.** 따라서 Admin의 상위 탭을 새로 만들지 말고 `OcrPanel.tsx` 입력 카드 안에 Segmented Control 형태의 전환 UI를 둔다.

권장 Label은 다음과 같다.

```text
[ 파일 업로드 ] [ 웹페이지 URL ]
```

`웹 URL`, `URL 업로드`도 기술적으로는 이해할 수 있지만 사용자 화면에서는 `웹페이지 URL`이 무엇을 입력하는지 더 명확하다. URL은 서버에 파일을 올리는 동작이 아니므로 `URL 업로드`라는 표현은 사용하지 않는다.

권장 화면 구조:

```text
문서 입력 방식

[ 파일 업로드 ] [ 웹페이지 URL ]

┌────────────────────────────────────────────┐
│ 선택한 방식의 입력 영역                    │
│                                            │
│ 파일 모드                                  │
│ Dropzone → 선택 파일 정보 → 파일 미리보기 │
│                                            │
│ 또는                                       │
│                                            │
│ 웹페이지 URL 모드                          │
│ URL 입력 → 미리보기 확인 → Domain/링크     │
└────────────────────────────────────────────┘

공통 Chunk 설정
→ 입력 방식에 맞는 분석 버튼
→ 공통 분석 결과 영역
→ 공통 VectorDB 저장 버튼
```

입력 방식별 표시 내용:

| 선택 모드 | 입력 영역 | 보조 정보 | 분석 버튼 |
|---|---|---|---|
| 파일 업로드 | 기존 `OcrDropzone` | `SelectedFile`, `OcrFilePreview` | `문서 분석 테스트` |
| 웹페이지 URL | 신규 `OcrUrlInput` | `OcrWebPreview`, Domain, 새 탭 링크 | `웹페이지 가져와 분석` |

Chunk 설정과 결과 영역을 입력 방식별로 두 벌 만들지 않는다. 다음 컴포넌트는 두 모드가 공유한다.

- `OcrChunkSettings`
- 분석 진행률
- `OcrResultSummary`
- 추출 Text 미리보기
- Chunk 목록
- 품질 메모
- VectorDB 저장 버튼과 저장 결과

권장 컴포넌트 조립 구조:

```text
OcrPanel
├─ OcrSourceSelector
├─ 선택된 입력 영역
│  ├─ FileInputPanel
│  │  ├─ OcrDropzone
│  │  ├─ SelectedFile
│  │  └─ OcrFilePreview
│  └─ WebUrlInputPanel
│     ├─ OcrUrlInput
│     └─ OcrWebPreview
├─ OcrChunkSettings
├─ 공통 분석 버튼
└─ OcrResultSummary
```

현재 컴포넌트 수가 적다면 `FileInputPanel`, `WebUrlInputPanel` 파일을 반드시 새로 만들 필요는 없다. 다만 `OcrPanel.tsx` 안에서 파일과 URL의 조건부 Rendering 경계가 한눈에 보이게 하고, 파일용 `OcrDropzone`이나 `OcrFilePreview` 안에 URL 분기를 추가하지 않는다.

다음 형태는 피한다.

- Admin 상위 탭을 `파일 OCR`, `웹 OCR`로 다시 분리
- 파일 Dropzone과 URL 입력창을 한 화면에 동시에 노출
- 입력 방식별 Chunk 설정과 결과 컴포넌트를 중복 구현
- URL 입력 중 매 Key 입력마다 외부 페이지를 자동 요청
- URL 기능을 `URL 업로드`라고 표시
- `OcrFilePreview`에 URL Preview 책임까지 추가

### 6.3 입력 모드 전환 동작

파일과 URL이 동시에 남지 않도록 `OcrSourceSelector` 변경을 하나의 명시적인 상태 전이로 처리한다.

```text
파일 → 웹페이지 URL 전환
→ 선택 File과 Object URL 정리
→ 이전 분석 결과·오류·저장 상태 초기화
→ 빈 URL 입력 화면 표시

웹페이지 URL → 파일 전환
→ URL과 iframe Preview 정리
→ 이전 분석 결과·오류·저장 상태 초기화
→ 빈 Dropzone 표시
```

세부 정책:

- 분석 중에는 입력 모드 전환을 비활성화하는 방식을 우선한다.
- 전환을 허용한다면 현재 `AbortController`를 먼저 취소한 뒤 상태를 초기화한다.
- 분석 완료 결과나 저장 전 결과가 있는 상태에서 모드를 바꾸면 즉시 초기화하되, 데이터 손실 안내가 필요하다고 판단되면 짧은 확인 Dialog를 사용할 수 있다.
- 파일 Object URL은 기존처럼 `URL.revokeObjectURL()`로 해제한다.
- URL iframe은 선택 모드가 바뀌면 DOM에서 제거한다.
- Chunk Size와 Overlap은 입력 종류와 무관한 사용자 설정이므로 모드 전환 후에도 유지하는 것을 권장한다.
- 저장 성공 상태는 Source가 바뀌면 반드시 초기화한다.

`canAnalyze`도 Source 종류를 기준으로 계산한다.

```typescript
const canAnalyze =
  source?.type === 'file'
    ? Boolean(source.file) && status !== 'loading'
    : source?.type === 'url'
      ? isValidWebUrl(source.url) && status !== 'loading'
      : false;
```

### 6.4 URL 입력 검증

Frontend 검증은 사용자 경험을 위한 1차 검증일 뿐 보안 검증이 아니다.

- 앞뒤 공백 제거
- `new URL(value)`로 파싱 가능한지 확인
- `http:`와 `https:`만 허용
- URL 길이는 현재 DB `original_file_url VARCHAR(500)` 계약에 맞춰 최대 500자로 제한
- 사용자명·비밀번호가 포함된 URL은 거부
- 빈 URL이면 분석 버튼 비활성화

`localhost`, 사설 IP 차단은 Frontend 결과를 신뢰하지 말고 Backend에서 다시 수행한다.

### 6.5 웹 미리보기

1차 구현에서는 브라우저 기반 미리보기를 **best effort**로 제공한다.

- 타이핑할 때마다 외부 페이지를 자동 로드하지 않는다.
- 사용자가 `미리보기`를 누른 뒤 확정된 URL만 iframe에 넣는다.
- iframe에는 `sandbox`를 적용하고 `allow-scripts`, `allow-forms`, `allow-top-navigation`을 주지 않는다.
- 항상 `새 탭에서 열기` 링크와 대상 Domain을 함께 표시한다.
- 외부 사이트의 `X-Frame-Options` 또는 CSP `frame-ancestors`로 표시가 차단될 수 있음을 안내한다.
- iframe 성공 여부를 Backend 수집 가능 여부로 판단하지 않는다.

URL 입력 영역은 다음과 같이 구성한다.

```text
웹페이지 URL

[ https://example.com/article                     ]
[미리보기]                         [입력 내용 지우기]

example.com
외부 사이트 정책에 따라 화면 미리보기가 제한될 수 있습니다.
[새 탭에서 원본 열기]
```

미리보기가 차단되어도 URL 분석 버튼은 Backend URL 검증 결과와 별개로 동작해야 한다. 사용자에게는 iframe 자체보다 Domain, 정규화된 URL, 새 탭 링크, 분석 완료 후 페이지 제목과 추출 Text가 더 신뢰할 수 있는 확인 정보다.

브라우저 iframe은 원본 페이지의 서버에 직접 요청하므로 관리자 IP와 접속 사실이 외부 사이트에 전달될 수 있다. 이를 허용할 수 없다면 자동 iframe을 제거하고 제목·Domain·새 탭 링크만 보여준 뒤, 2차 구현에서 서버가 만든 Sanitized Preview를 `srcDoc`으로 제공한다.

원본 HTML을 그대로 `srcDoc`에 넣거나 `dangerouslySetInnerHTML`로 렌더링하면 안 된다.

### 6.6 API Adapter

`apiAdminAiService.analyzeDocument()`는 Source에 따라 Job 생성 Endpoint만 분기하고 이후 Polling은 공유한다.

```text
sourceType=file
→ FormData
→ POST /admin/ocr/jobs

sourceType=url
→ JSON { url, chunkSize, overlap }
→ POST /admin/ocr/url-jobs

공통
→ GET /admin/ocr/jobs/{jobId}
→ completed/failed까지 Polling
```

Polling Loop를 복사하지 말고 `pollOcrJob(jobId, signal, onProgress)`와 같은 내부 함수로 추출한다.

### 6.7 결과 표시

`OcrDocumentPayload`에 다음 Source Meta를 추가한다.

```typescript
sourceType: 'file' | 'url';
sourceUrl: string | null;
```

파일 결과와의 하위 호환이 필요하면 Backend 기본값을 `file`, `sourceUrl=null`로 둔다.

웹 결과에서는 파일 확장자로 단위를 판단하지 않는다.

- `documentName`: 페이지 `<title>` 또는 Hostname
- `pageCount`: `null`
- 단위 Label: `웹페이지`
- `sourceUrl`: 검증과 Redirect가 끝난 최종 URL
- notes: 본문 추출 방식, OCR 처리 이미지 수, 건너뛴 이미지와 동적 페이지 경고

Chunk의 React `key`로 Text 원문만 사용하면 같은 Text가 중복될 때 Key가 충돌한다. URL 기능을 수정하면서 `key={`${index}-${text.slice(0, 32)}`}`처럼 Index를 포함하도록 같이 보완한다.

---

## 7. Backend API와 Schema 수정 지시

### 7.1 신규 Request

`backend/app/schemas/admin.py`에 다음 요청 계약을 추가한다.

```python
class OcrUrlJobRequest(AdminSchema):
    url: str = Field(min_length=1, max_length=500)
    chunk_size: int = Field(default=512, alias="chunkSize", ge=100, le=4096)
    overlap: int = Field(default=50, ge=0)

    @model_validator(mode="after")
    def validate_options(self) -> "OcrUrlJobRequest":
        # 공백 URL, scheme, credentials, overlap < chunk_size를 검증한다.
        ...
```

Pydantic 검증만으로 SSRF 방어를 끝내지 않는다. DNS 해석과 Redirect 대상 검증은 Fetcher에서 수행한다.

### 7.2 기존 Response 확장

`OcrDocumentResponse`에 하위 호환 가능한 기본값을 둔다.

```python
source_type: Literal["file", "url"] = Field(default="file", alias="sourceType")
source_url: str | None = Field(default=None, alias="sourceUrl", max_length=500)
```

기존 테스트 Fixture가 새 필드를 작성하지 않아도 파일 결과로 해석되어야 한다. URL 저장 시에는 `source_type="url"`과 최종 검증 URL을 반드시 넣는다.

### 7.3 신규 Endpoint

```text
POST /api/admin/ocr/url-jobs
Content-Type: application/json
```

Request 예시:

```json
{
  "url": "https://example.org/article",
  "chunkSize": 512,
  "overlap": 50
}
```

Response는 기존과 같다.

```json
{
  "jobId": "...",
  "status": "queued"
}
```

이후 조회와 저장 Endpoint는 변경하지 않는다.

```text
GET  /api/admin/ocr/jobs/{jobId}
POST /api/admin/ocr/vector-save
```

### 7.4 HTTP 오류 원칙

Job 등록 전에 확인할 수 있는 오류는 즉시 HTTP 오류로 반환한다.

| 상황 | 권장 상태 |
|---|---:|
| URL 형식, Scheme, Credentials, Chunk 옵션 오류 | 422 |
| 동시 Job 한도 초과 | 429 |
| Job 없음/만료 | 404 |

DNS, Redirect, 원격 응답, HTML 크기, Image 처리 오류처럼 Job 내부에서 발생하는 오류는 기존 구조에 맞춰 Job을 `failed`로 만들고 안전한 메시지를 `error`에 넣는다. 내부 IP, 실제 해석 주소, 시스템 예외, 응답 본문은 사용자 메시지나 로그에 그대로 노출하지 않는다.

---

## 8. URL 수집 보안 지시

웹 URL 입력은 Backend가 사용자가 지정한 주소로 요청을 보내는 기능이다. 일반 파일 업로드보다 공격면이 크므로 SSRF 방어를 선택 기능으로 취급하면 안 된다.

### 8.0 관리자 인증은 배포 선행 조건

현재 `backend/app/api/admin/router.py`의 OCR·LLM Endpoint에는 `require_admin` Dependency가 없고, `backend/app/api/router.py`에서 `/api/admin` Router가 항상 Mount된다. 반면 Dashboard와 일부 LLM API에는 이미 `app.api.auth.dependencies.require_admin` 구현이 사용된다.

URL Fetch Endpoint를 인증 없이 공개하면 외부 사용자가 서버 Network를 대신 호출하게 만들 수 있다. 따라서 다음 중 하나를 완료하지 않은 상태로 URL 기능을 배포하면 안 된다.

1. 권장: Admin Router 전체에 `Depends(require_admin)`을 적용해 기존 OCR·LLM·평가 Endpoint까지 관리자 전용으로 만든다.
2. 최소: 신규 `POST /ocr/url-jobs`에라도 `require_admin`을 필수로 적용한다.
3. Admin 기능을 운영에서 사용하지 않는 배포판은 설정으로 Frontend Admin Route와 Backend Admin Router Mount를 모두 제외한다.

Frontend Route를 숨기거나 메뉴를 제거하는 것만으로는 직접 HTTP 호출을 막을 수 없다. 인증 적용 시 기존 Admin Frontend의 `apiClient`가 Access Token을 보내는지 확인하고, API Test도 비인증 401·일반 사용자 403·관리자 성공을 함께 검증한다.

### 8.1 URL 기본 검증

- Scheme은 `http`, `https`만 허용한다.
- `file:`, `ftp:`, `data:`, `javascript:` 등은 거부한다.
- 사용자명 또는 비밀번호가 포함된 URL은 거부한다.
- Fragment는 요청 전에 제거한다.
- Host가 없으면 거부한다.
- 1차 구현에서는 HTTP 80, HTTPS 443의 기본 Port만 허용한다.
- `localhost`, `.localhost`, `.local` Host를 거부한다.
- 국제화 Domain은 IDNA ASCII 형태로 정규화한 뒤 검증한다.

### 8.2 DNS와 IP 검증

Host를 A/AAAA로 해석한 모든 주소를 검사한다. 하나라도 아래 범위면 요청하지 않는다.

- Loopback
- Private network
- Link-local
- Multicast
- Unspecified
- Reserved
- IPv4-mapped IPv6의 내부 주소
- Cloud Metadata 주소 예: `169.254.169.254`

문자열 Prefix 비교로 IP를 판정하지 말고 Python `ipaddress` 기준으로 검사한다.

DNS 검증 뒤 실제 연결 사이에 주소가 바뀌는 DNS Rebinding 위험이 남는다. 운영 환경에서는 애플리케이션 검증만 믿지 말고 Cloud Run/VPC/Firewall 또는 전용 Egress Proxy에서 내부 대역 접근을 한 번 더 차단한다.

### 8.3 Redirect

- 자동 무제한 Redirect를 사용하지 않는다.
- 최대 3회처럼 작은 횟수로 제한한다.
- 각 `Location`을 현재 URL 기준으로 정규화한다.
- 매 Redirect 대상마다 Scheme, Host, Port, DNS/IP 검증을 다시 실행한다.
- 최종 URL만 결과와 DB에 기록한다.
- HTTPS에서 HTTP로 내려가는 Redirect는 기본 거부를 권장한다.

### 8.4 HTTP Client

- Runtime 의존성으로 HTTP Client를 명시적으로 추가한다.
- Connect/Read/Total Timeout을 각각 설정한다.
- 시스템 Proxy 환경변수를 의도치 않게 따르지 않도록 `trust_env` 정책을 명시한다.
- Cookie Jar, 사용자 인증 Header, Frontend Cookie를 전달하지 않는다.
- 서비스 전용 User-Agent를 사용한다.
- 응답은 한 번에 `response.content`로 전부 읽지 말고 Streaming으로 제한 크기까지만 받는다.
- URL 전체 Query는 Token을 포함할 수 있으므로 로그에 원문 URL을 남기지 않는다. 최소한 Query와 Fragment를 제거한 Origin/Path 또는 Hash만 기록한다.

### 8.5 HTML 제한

권장 초기값:

| 설정 | 권장 기본값 | 목적 |
|---|---:|---|
| `OCR_WEB_MAX_URL_LENGTH` | 500 | 현재 DB 컬럼과 일치 |
| `OCR_WEB_MAX_HTML_SIZE_MB` | 5 | 메모리·파서 공격 제한 |
| `OCR_WEB_MAX_TEXT_CHARS` | 100,000 | Job/Gemini 과부하 제한 |
| `OCR_WEB_MAX_CHUNKS` | 200 | Gemini 요청량·Neon 행 증가 제한 |
| `OCR_WEB_MAX_REDIRECTS` | 3 | Redirect Loop·우회 방지 |
| `OCR_WEB_CONNECT_TIMEOUT_SECONDS` | 5 | 연결 대기 제한 |
| `OCR_WEB_READ_TIMEOUT_SECONDS` | 15 | 느린 응답 제한 |

허용 Content-Type은 우선 `text/html`, `application/xhtml+xml`로 제한한다. URL이 PDF나 Office 파일을 직접 가리키는 경우 1차 URL 기능에서 거부하고 기존 파일 업로드를 안내한다. 후속 구현에서 원격 파일 다운로드를 지원하려면 최종 Content-Type과 Binary Signature를 확인한 뒤 기존 파일 OCR로 명시적으로 연결한다.

### 8.6 Image 제한

모든 Image URL에도 페이지와 같은 SSRF/Redirect 검증을 적용한다. CDN Domain이라고 예외 처리하지 않는다.

권장 초기값:

| 설정 | 권장 기본값 |
|---|---:|
| `OCR_WEB_MAX_IMAGES` | 20 |
| `OCR_WEB_MAX_IMAGE_SIZE_MB` | 5 |
| `OCR_WEB_MAX_TOTAL_IMAGE_SIZE_MB` | 30 |
| `OCR_WEB_IMAGE_CONCURRENCY` | 4 |
| 최소 가로/세로 | 64px |
| 최대 Pixel | 기존 `OCR_MAX_IMAGE_PIXELS` 재사용 |

1차 허용 형식은 JPEG, PNG, WebP 같은 Raster Image로 한정한다. 다음은 건너뛰고 notes에 요약한다.

- SVG
- GIF Animation
- Data URL
- Blob URL
- 추적 Pixel과 너무 작은 Icon
- 중복 URL 또는 동일 Content Hash
- 허용 크기·Pixel 초과
- Content-Type과 실제 Image 형식 불일치

Image 실패 하나 때문에 본문 전체 Job을 실패시키지 않는다. HTML 본문이 정상이라면 경고를 추가하고 나머지 Image 처리를 계속한다. 반대로 HTML 자체를 가져오지 못하거나 추출 Text가 완전히 비어 있으면 Job을 실패 또는 `review`로 처리하는 정책을 명확히 테스트한다.

---

## 9. HTML 본문과 Image OCR 결합 지시

### 9.1 HTML 구조 추출

기존 `lxml`을 사용해 1차 구현을 만들 수 있다. 다음 요소는 제거한다.

```text
script, style, noscript, template, nav, footer, form, iframe, canvas
```

`main`, `article`을 우선하고 없으면 `body`를 사용한다. 다음 구조는 Markdown과 유사한 Plain Text로 변환한다.

- `h1`~`h6`: 제목 Level
- `p`: 문단
- `ul`, `ol`, `li`: 목록
- `table`, `tr`, `th`, `td`: 단순 표
- `blockquote`, `pre`, `code`: 의미가 유지되는 Text
- `br`: 줄바꿈

반복 공백, 숨김 요소, 비어 있는 Block을 제거한다. 같은 문단이 여러 번 나타나는 사이트를 고려해 완전 동일 Block의 연속 중복을 제거하되, 내용이 같은 정상 목록을 과도하게 삭제하지 않는다.

정적 HTML에 본문이 거의 없고 Script Bundle만 있는 경우 Browser Rendering을 즉시 추가하지 않는다. 결과 notes에 “JavaScript 렌더링 페이지일 수 있음”을 남기고 `review`로 분류한다.

### 9.2 Image 후보

- DOM에 나타난 순서대로 후보를 수집한다.
- `src`, 필요한 경우 `srcset`의 적절한 후보를 사용한다.
- Lazy Load 사이트의 `data-src` 계열은 허용 목록을 정해 처리한다.
- 상대 URL은 **Redirect 완료 후 최종 페이지 URL**을 Base로 `urljoin`한다.
- `alt`, 주변 Caption, DOM 순번을 OCR 결과의 Label로 보존한다.
- CSS Background Image는 1차 범위에서 제외한다.

### 9.3 결합 Text

최종 Text는 최소한 출처를 구분할 수 있어야 한다.

```text
# 페이지 제목

웹페이지 본문 문단...

## 웹페이지 이미지 OCR

### 이미지 1 - 대체 텍스트 또는 캡션
이미지에서 추출된 Text...

### 이미지 2
이미지에서 추출된 Text...
```

Image OCR Text를 본문과 무작정 이어 붙이지 않는다. Chunk만 읽어도 이것이 이미지에서 나온 Text인지 알 수 있게 Heading을 넣는다.

HTML 본문은 OCR Confidence 개념이 없다. 최종 `confidence`는 다음처럼 해석 규칙을 고정한다.

- OCR 성공 Image가 있으면 해당 OCR Line의 평균 Confidence
- OCR 대상 Image가 없고 본문 Text가 있으면 `100.0`
- OCR Image가 모두 실패하거나 본문이 매우 짧으면 notes와 `readiness=review`로 보완

`DOCUMENT_TYPE_LABELS`에 `web_page: 웹페이지`를 추가하고 notes에 HTML 본문 문자 수, OCR 성공/건너뜀 Image 수를 기록한다.

### 9.4 Prompt Injection 성격의 Text

웹 본문에 “이전 지시를 무시하라” 같은 문장이 있어도 수집 단계에서는 일반 문서 Text로 저장된다. 이후 RAG Prompt에 넣을 때는 검색 문서를 명령이 아니라 인용 자료로 취급하는 별도 방어가 필요하다. URL 수집기가 HTML 안의 지시문을 실행하거나 설정값으로 해석하면 안 된다.

---

## 10. Job Manager 수정 지시

기존 공개 파일 메서드는 유지한다.

```python
create_job(file, chunk_size, overlap)
```

URL용 메서드를 추가한다.

```python
create_url_job(url, chunk_size, overlap)
```

두 메서드는 다음 공통 로직만 내부 Helper로 재사용한다.

- 만료 Job 제거
- 활성 Job 수 확인
- Job ID 생성
- 초기 `OcrJobRecord` 저장
- Task 보관과 Done Callback

파일 처리와 URL 처리는 입력과 자원 제한이 다르므로 하나의 `UploadFile` 형태로 위장하지 않는다.

```text
_run_file_job()
→ 기존 file processor

_run_url_job()
→ WebOcrWorkflowService.process_url()
```

예상 가능한 웹 Domain 오류는 안전한 실패 메시지로 변환한다. 모든 오류를 `except Exception` 하나에만 맡기면 URL 검증 실패와 내부 버그를 구분할 수 없다.

Job 총량만 제한하면 하나의 URL이 Image 20개를 내려받는 동안 자원을 오래 점유할 수 있다. URL Job도 기존 `OCR_MAX_PENDING_JOBS`에 포함하고 Image 다운로드 동시성은 Job 내부 Semaphore로 별도 제한한다.

---

## 11. 기존 Vector 저장 유지 지시

이번 작업에서는 Embedding 생성과 Neon 저장 방식을 변경하지 않는다. 파일과 URL Job 모두 완료된 `OcrDocumentResponse.chunks`를 기존 `save_ocr_result_with_embeddings()`에 전달한다.

```text
변경하지 않는 저장 흐름

POST /api/admin/ocr/vector-save { jobId }
→ save_ocr_result_with_embeddings()
→ embedding_service = GeminiEmbeddingService
→ gemini-embedding-001
→ RETRIEVAL_DOCUMENT, 1024차원
→ DocumentRepository.save_with_chunks()
→ admin_documents 1행
→ document_chunks N행 + embedding VECTOR(1024)
→ 기존 단일 Transaction Commit/Rollback
```

다음 파일과 계약은 이번 기능에서 수정하지 않는다.

- `backend/app/services/embedding_service.py`
- `backend/app/core/rag_embedding.py`
- `backend/app/services/document_ingestion_service.py`
- `backend/app/repositories/document_chunk.py`
- `backend/app/models/generated.py`의 Vector 컬럼
- `backend/migrations/versions/*`의 Vector Schema
- `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION`
- `RAG_EMBEDDING_*`

허용되는 저장 인접 변경은 URL Job의 Source Reference 결정뿐이다. `save_ocr_result_with_embeddings()`는 완료 Job의 `sourceType`과 `sourceUrl`을 읽어 `original_file_url` 값을 구분할 수 있다. 이 분기는 Embedding Provider, Vector 값, 차원 또는 저장 테이블을 변경하지 않는다.

```text
파일 Job
→ 기존 ocr-job://{jobId}/{encodedName}

URL Job
→ 검증된 최종 HTTP(S) URL
```

Frontend가 저장 요청에 URL을 다시 보내게 하면 안 된다. 사용자가 저장 시점에 URL을 변조할 수 있고, 실제로 수집한 최종 URL과 달라질 수 있기 때문이다.

권장 Helper:

```python
def build_source_reference(job_id: str, result: OcrDocumentResponse) -> str:
    if result.source_type == "url":
        if not result.source_url:
            raise OcrSaveValidationError("웹페이지 원본 URL을 확인할 수 없습니다.")
        return result.source_url
    return _build_job_file_reference(job_id, result.document_name)
```

현재 `admin_documents.original_file_url`은 `VARCHAR(500)`이다. 1차 구현에서는 입력과 Redirect 최종 URL을 500자 이하로 제한하면 Migration 없이 재사용할 수 있다. 500자를 넘는 URL도 제품 요구사항이라면 제한을 조용히 늘리지 말고 별도 Alembic Migration으로 컬럼을 `TEXT` 또는 합의된 길이로 변경하고 `generated.py` 모델도 실제 DB와 함께 갱신한다.

이번 범위에서는 Migration을 만들지 않는 것을 우선하므로 500자를 넘는 최종 URL은 저장 전에 명시적으로 거부한다.

동일 URL을 여러 번 저장하면 현재 구조에서는 새 문서가 중복 생성된다. 기존 파일 Job도 API 수준 Idempotency가 없으므로 1차 범위에서는 기존 동작을 유지하되, 화면과 문서에 중복 가능성을 표시한다. URL 최신화·Upsert·버전 관리는 후속 정책으로 분리한다.

---

## 12. 설정과 의존성

`backend/app/core/config.py`와 `.env.example`에 웹 수집 제한을 명시한다.

```text
OCR_WEB_MAX_URL_LENGTH=500
OCR_WEB_MAX_HTML_SIZE_MB=5
OCR_WEB_MAX_TEXT_CHARS=100000
OCR_WEB_MAX_CHUNKS=200
OCR_WEB_MAX_REDIRECTS=3
OCR_WEB_CONNECT_TIMEOUT_SECONDS=5
OCR_WEB_READ_TIMEOUT_SECONDS=15
OCR_WEB_MAX_IMAGES=20
OCR_WEB_MAX_IMAGE_SIZE_MB=5
OCR_WEB_MAX_TOTAL_IMAGE_SIZE_MB=30
OCR_WEB_IMAGE_CONCURRENCY=4
```

Gemini 무료 사용량과 기존 Neon 저장 부하를 보호하기 위해 웹페이지 Text와 최종 Chunk 개수에 별도 상한을 둔다. `OCR_WEB_MAX_CHUNKS` 검사는 웹 Workflow에서 기존 `create_chunks()` 실행 직후, 저장 버튼을 누르기 전에 수행한다. Chunk를 조용히 앞부분만 잘라 저장하지 말고 Chunk Size를 늘리거나 더 작은 페이지를 입력하도록 오류를 반환한다.

이 제한은 신규 웹 URL 입력에만 적용한다. 기존 파일 OCR의 Chunk 정책과 Embedding 코드는 이번 작업에서 변경하지 않는다.

URL fetch에 사용하는 HTTP Client는 `backend/requirements.txt`에 직접 선언한다. TestClient 또는 다른 라이브러리의 전이 의존성으로 우연히 설치된 패키지에 기대지 않는다.

HTML 구조 추출은 이미 OCR 의존성에 포함된 `lxml`로 시작한다. 본문 품질이 실제 Fixture에서 부족할 때만 Trafilatura 같은 본문 추출 라이브러리를 비교 평가하고 추가한다. JavaScript 렌더링을 위해 처음부터 Playwright/Chromium을 Backend Image에 넣지 않는다. 현재 PaddleOCR도 무거우므로 Browser Runtime까지 한 프로세스에 합치면 Image 크기, Cold Start, 메모리와 동시성 문제가 커진다.

---

## 13. 단계별 구현 순서

### Phase 0. 기존 회귀 기준 고정

1. 현재 파일 Job API, Polling, Vector 저장 테스트를 먼저 실행한다.
2. 파일 OCR Response JSON과 UI 동작을 기준선으로 기록한다.
3. 기존 테스트 Fixture에 `sourceType` 기본값을 추가해도 파일 계약이 유지되는지 확인한다.

### Phase 1. Framework 독립 Web Extractor

1. HTML에서 제목, 본문 Block, Image 후보를 추출하는 계약을 만든다.
2. Network 없는 HTML Fixture로 Boilerplate 제외, 목록·표, 상대 Image URL, DOM 순서를 테스트한다.
3. 기존 이미지 전처리와 Paddle Engine을 주입받아 Image OCR Text를 결합한다.
4. `ai/ocr`에서 `fastapi`, `app.*`, HTTP Client Import가 없는지 확인한다.

### Phase 2. 안전한 Fetcher

1. URL 정규화와 DNS/IP 검사 함수를 만든다.
2. Redirect 각 단계에 같은 검사를 적용한다.
3. Streaming 크기 제한과 Content-Type 검사를 적용한다.
4. Image별/전체 크기, 개수, Pixel, 동시성 제한을 적용한다.
5. HTTP Mock Transport와 Resolver 주입으로 외부 Network 없는 테스트를 작성한다.

### Phase 3. Web Workflow와 Job

1. `WebOcrWorkflowService.process_url()` 중심 함수를 구현한다.
2. 진행률 Stage를 연결한다.
3. `OcrJobManager.create_url_job()`과 `_run_url_job()`을 추가한다.
4. URL Job도 기존 상태 조회 Response로 완료/실패를 확인한다.

권장 진행 단계:

```text
queued 3
→ validating_url 8
→ fetching_page 15
→ parsing_html 30
→ fetching_images 45
→ ocr_images 55~80
→ cleaning 86
→ chunking 93~97
→ finalizing 99
→ completed 100
```

### Phase 4. API와 Frontend

1. URL Job Schema와 Router Endpoint를 추가한다.
2. Frontend Source Union과 입력 모드 UI를 추가한다.
3. API Adapter의 Job 생성만 분기하고 Polling을 공통화한다.
4. URL 미리보기 실패가 분석 요청 실패로 연결되지 않게 한다.
5. 결과 화면에서 Source URL과 웹페이지 단위를 표시한다.

### Phase 5. 저장과 회귀 검증

1. URL Job은 최종 URL을 `original_file_url`에 저장한다.
2. 기존 Chunk 순서와 개수로 Gemini Embedding을 생성한다.
3. 파일 Job은 계속 `ocr-job://` Reference를 저장한다.
4. 파일/URL 모두 저장 실패 시 전체 Transaction이 Rollback되는지 확인한다.
5. `embedding_service.py`, `chunk_embeddings`, RAG Provider와 Vector Schema에 Diff가 없는지 확인한다.
6. 웹 URL 결과가 `OCR_WEB_MAX_CHUNKS`를 넘으면 Gemini 호출 전에 실패하는지 확인한다.

### Phase 6. 문서화

구현 완료 후 실제 최종 코드 기준으로 `docs/2_reports`에 별도 RPT 문서를 작성한다. 이 PRM 지시서를 구현 완료 보고서처럼 수정하지 않는다.

---

## 14. 테스트 지시

### 14.1 AI Core Unit Test

`tests/ai/ocr/test_web_extractor.py`

- `<title>`과 본문 추출
- Script/Style/Nav/Footer/Form 제외
- Heading, Paragraph, List, Table 순서
- 상대/절대 Image URL 정규화
- `srcset`, Lazy Image 후보
- 중복 Image 제거
- 본문 + Image OCR Section 결합
- OCR Image 없음/일부 실패/전체 실패
- Dynamic Page로 의심되는 빈 본문 경고
- `ai/ocr`의 Backend 독립성

### 14.2 Fetcher Unit Test

`backend/tests/test_web_document_fetcher.py`

- `http`, `https`만 허용
- Credentials와 비표준 Port 거부
- localhost, IPv4/IPv6 사설·Loopback·Link-local 차단
- DNS가 여러 주소를 반환할 때 내부 주소 하나라도 있으면 차단
- Redirect마다 재검증
- Redirect 횟수 초과
- HTML Content-Type 거부
- HTML Streaming 크기 초과
- Timeout과 연결 실패의 안전한 오류 메시지
- Image 개수·개별 크기·전체 크기·형식·Pixel 제한
- Image Redirect를 내부 IP로 바꾸는 우회 차단

실제 인터넷을 호출하는 테스트를 기본 Test Suite에 넣지 않는다. HTTP Client와 DNS Resolver를 주입하거나 Mock 처리한다.

### 14.3 Workflow와 Job Test

`backend/tests/test_web_ocr_workflow.py`, `test_ocr_jobs.py`

- URL 검증이 Chunking보다 먼저 실행
- Progress가 역행하지 않음
- HTML 본문과 OCR Text가 Response에 포함
- `pageCount=null`, `sourceType=url`, `sourceUrl=final_url`
- 정상 URL Job의 `queued → processing → completed`
- Domain 오류의 `failed`
- 파일/URL Job이 같은 Capacity에 포함
- TTL 이후 완료 Job 제거

### 14.4 API Contract Test

`backend/tests/test_admin_ocr_api.py`

- `POST /api/admin/ocr/url-jobs` JSON Alias
- 정상 요청 202와 기존 Job Created 계약
- 잘못된 URL/Chunk 422
- Capacity 초과 429
- 비인증 401, 일반 사용자 403, 관리자 202
- 기존 Multipart 파일 Endpoint 회귀 없음

### 14.5 Vector 저장 Test

`backend/tests/test_ocr_vector_save.py`

- 파일 Job은 기존 `ocr-job://` 저장
- URL Job은 Backend가 보관한 최종 URL 저장
- URL을 저장 Request에서 받지 않음
- Chunk와 Embedding 개수·순서·1024차원 유지
- URL 누락/길이 초과 시 저장 전 명시적 실패
- DB 예외 시 문서와 모든 Chunk Rollback

### 14.6 Frontend 검증

- 기존 OCR 상위 탭 안에서 `파일 업로드`/`웹페이지 URL` 입력 방식만 전환되는지 확인
- 파일 Dropzone과 URL 입력창이 동시에 표시되지 않는지 확인
- 파일/URL 모드 전환 시 이전 상태 초기화
- 모드 전환 후 Chunk Size와 Overlap은 유지되고 분석·저장 결과만 초기화되는지 확인
- 파일 버튼은 `문서 분석 테스트`, URL 버튼은 `웹페이지 가져와 분석`으로 표시되는지 확인
- URL 형식 오류와 버튼 비활성화
- 분석 중 입력과 모드 전환 정책
- Abort 시 Polling 중단
- iframe 차단 사이트의 Fallback 안내
- URL Job 완료 후 Text와 Chunk 표시
- 저장 성공 후 중복 저장 버튼 비활성화
- `npm run build`
- Playwright가 있다면 파일/URL 두 경로의 기본 E2E 추가

### 14.7 권장 실행 명령

Repository Root 기준 실제 프로젝트 구조에 맞춰 다음과 같이 확인한다.

```powershell
.\backend\.venv\Scripts\python.exe -B -m unittest discover -s backend\tests -t backend -p "test_*.py" -v
.\backend\.venv\Scripts\python.exe -B -m pytest tests\ai\ocr
cd frontend
npm run build
```

Paddle 모델 다운로드와 실제 외부 URL 접근이 필요한 Smoke Test는 기본 Unit Test와 분리한다.

---

## 15. 수동 검증 시나리오

최소 다음 종류의 페이지를 검증한다. 테스트 URL 자체는 운영 문서에 고정하지 말고 팀이 통제하는 Fixture Server를 우선 사용한다.

1. 제목·문단만 있는 정적 HTML
2. 목록과 표가 있는 페이지
3. 상대 경로 PNG/JPEG가 포함된 페이지
4. 외부 CDN Image가 포함된 페이지
5. Image 일부가 404인 페이지
6. 본문 없이 JavaScript Bundle만 있는 페이지
7. Redirect 1회 후 정상 HTML
8. Redirect가 localhost/사설 IP로 향하는 공격 Fixture
9. HTML 또는 Image 크기 제한을 넘는 Fixture
10. iframe 표시를 금지하지만 Backend HTML 수집은 가능한 페이지

각 정상 시나리오에서 다음을 확인한다.

```text
URL 입력
→ 미리보기 또는 Fallback
→ Job 생성 202
→ 진행률 Polling
→ 최종 URL/제목/Text/Image OCR/Chunk 확인
→ VectorDB 저장
→ documentId와 chunkCount 확인
→ DB original_file_url이 최종 URL인지 확인
```

---

## 16. 관측성과 개인정보

로그에는 다음을 남긴다.

- Job ID
- Source Type
- Query를 제거한 Host 또는 URL Hash
- Redirect 횟수
- HTML byte와 추출 문자 수
- Image 후보/성공/건너뜀 수
- OCR 처리 시간
- Chunk 수

다음은 남기지 않는다.

- URL Query 전체
- Cookie, Authorization Header
- HTML 원문 전체
- OCR Text 전체
- API Key, DB URL
- Image Binary

웹페이지에는 개인정보와 저작권 보호 콘텐츠가 포함될 수 있다. 수집 대상과 저장 기간, 외부 Gemini Embedding API로 Text가 전송된다는 사실, 삭제 요청 처리 정책을 운영 전에 확인한다.

---

## 17. 1차 구현에서 하지 않을 것

- 링크를 따라가는 다중 페이지 Crawler
- Sitemap/robots 기반 전체 사이트 수집
- 로그인 Cookie 또는 사용자 Browser Session 전달
- CAPTCHA 우회
- Playwright/Chromium 기반 JS Rendering
- Video Frame OCR
- SVG Text 분석
- CSS Background Image OCR
- 페이지 변경 주기 감시와 자동 재수집
- URL 중복 제거·Versioning·Upsert
- Admin OCR Vector를 상담 RAG `chunk_embeddings`로 자동 이관
- Gemini를 Sentence-Transformers 또는 다른 Embedding 모델로 교체
- `document_chunks.embedding` 저장 중단 또는 Legacy 마이그레이션
- `ai.rag.chunk_text()` 기반 RAG Chunk 정책으로 전환
- `document_ingestion_service.ingest_document()` 연결
- `chunk_embeddings` 생성·수정·삭제
- Vector 차원 또는 Provider Registry 변경
- 메모리 Job을 Redis/Celery/DB Queue로 전환

이 항목들을 한 번에 포함하면 웹 수집, Browser Automation, Queue, RAG 통합이라는 서로 다른 작업이 결합되어 테스트와 장애 범위가 크게 늘어난다.

---

## 18. 후속 확장 순서

1차 정적 HTML 구현의 실제 실패율과 대상 사이트를 측정한 뒤 다음 순서로 확장한다.

1. 본문 추출 품질 개선 라이브러리 A/B 비교
2. Sanitized Server Preview 또는 별도 Screenshot Worker
3. JavaScript 렌더링 전용 Browser Worker
4. URL Canonicalization과 중복/Version 정책
5. 예약 재수집과 변경 감지
6. Admin 저장 Embedding과 상담 RAG 검색 Embedding 통합
7. Redis/DB Queue와 다중 Worker 지원

Browser Rendering이 필요하면 PaddleOCR가 실행되는 API 프로세스 안에 Chromium을 바로 넣기보다 별도 Fetch/Render Worker를 우선 검토한다.

---

## 19. 구현 파일별 체크리스트

| 파일 | 구현 지시 | 완료 확인 |
|---|---|---|
| `frontend/.../types/ocr.ts` | File/URL Source Union, Source Meta | 파일 타입 회귀 없음 |
| `frontend/.../hooks/useOcrTest.ts` | 입력 전환, Analyze 분기, Abort/Reset | 이전 결과가 섞이지 않음 |
| `frontend/.../OcrPanel.tsx` | 입력 모드와 공통 설정 조립 | 파일/URL 상호 배타 |
| `frontend/.../OcrUrlInput.tsx` | URL 입력·기본 검증 | http/https만 허용 |
| `frontend/.../OcrWebPreview.tsx` | Sandbox Preview·Fallback | XSS와 자동 로드 방지 |
| `frontend/.../apiAdminAiService.ts` | URL Job 생성, Polling 공통화 | Poll Loop 중복 없음 |
| `backend/app/schemas/admin.py` | URL Request와 Source Meta | camelCase 계약 유지 |
| `backend/app/api/admin/router.py` | `/ocr/url-jobs` | Router에 수집 로직 없음 |
| `backend/app/services/ocr_job_service.py` | URL Job Task와 Capacity | 기존 File Job 유지 |
| `backend/app/services/web_document_fetcher.py` | SSRF·Redirect·Size·Timeout | 모든 Image URL 재검증 |
| `backend/app/services/web_ocr_workflow.py` | 전체 중심 흐름 | 위에서 아래로 단계 확인 |
| `ai/ocr/extractors/web.py` | HTML 구조와 Image OCR 결합 | Backend Import 없음 |
| `backend/app/services/ocr_workflow.py` | 공통 Response Builder 확장 | File/Web 중복 최소화 |
| `backend/app/services/admin_ocr.py` | Source Reference만 분기 | Gemini·Vector 저장 로직 불변 |
| `backend/app/core/config.py` | 웹 수집 한도 | `.env.example` 동기화 |
| `backend/requirements.txt` | HTTP Client 명시 | 전이 의존성 미사용 |
| Backend/AI Tests | 보안·계약·회귀 | 외부 Network 없는 자동 Test |

이번 작업의 변경 금지 확인 목록:

```text
backend/app/services/embedding_service.py
backend/app/core/rag_embedding.py
backend/app/services/document_ingestion_service.py
backend/app/repositories/document_chunk.py
backend/app/models/generated.py의 Vector 정의
backend/migrations/versions/*의 Vector Schema
ai/rag/embeddings/*
```

---

## 20. 코드 읽기 순서

구현자는 다음 순서로 현재 코드와 변경 코드를 읽는다.

```text
1. frontend/src/features/admin/hooks/useOcrTest.ts
   현재 파일 상태와 Job Polling 시작점
   ↓
2. frontend/src/features/admin/services/apiAdminAiService.ts
   Multipart Job 생성과 공통 Polling
   ↓
3. backend/app/api/admin/router.py
   기존 File Job/Status/Save HTTP 진입점
   ↓
4. backend/app/services/ocr_job_service.py
   메모리 Job과 Task 상태 전이
   ↓
5. backend/app/services/ocr_workflow.py
   파일 OCR, Chunk, Admin Response 중심 흐름
   ↓
6. ai/ocr/pipeline.py 및 ai/ocr/extractors/*
   Framework 독립 OCR Core와 재사용할 Image 처리
   ↓
7. backend/app/services/admin_ocr.py
   완료 Job → Embedding → 저장 중심 흐름
   ↓
8. backend/app/repositories/document_repository.py
   문서·Chunk Transaction
   ↓
9. 신규 web_document_fetcher.py
   URL/Redirect/HTML/Image 안전 수집
   ↓
10. 신규 ai/ocr/extractors/web.py
    HTML 본문과 Image OCR 결합
    ↓
11. 신규 web_ocr_workflow.py
    URL 기능 전체 Orchestrator
```

---

## 21. 최종 권장 흐름

```text
사용자 URL 입력
→ Frontend 기본 형식 검증
→ 선택적 Sandbox 미리보기
→ POST /api/admin/ocr/url-jobs
→ OcrJobManager.create_url_job()
→ WebOcrWorkflowService.process_url()
→ URL/DNS/Redirect SSRF 검증
→ 제한된 HTML 다운로드
→ HTML 제목·본문·Image 후보 추출
→ Image별 SSRF/크기/형식 검증과 다운로드
→ 기존 PaddleOCR 전처리·Engine
→ 본문 + Image OCR Text 통합
→ 기존 Text 정제
→ 기존 관리자용 문자 Chunk
→ OcrDocumentResponse
→ 기존 GET /api/admin/ocr/jobs/{jobId} Polling
→ 기존 결과 화면에 Text/Chunk 표시
→ 사용자 검토 후 기존 POST /api/admin/ocr/vector-save
→ 기존 Gemini 1024차원 Embedding
→ 기존 Neon Transaction 저장
```

이 구현의 핵심 원칙은 다음 네 가지다.

1. 파일 OCR 계약과 동작을 깨지 않는다.
2. URL 네트워크 수집은 AI Core가 아니라 Backend Adapter에서 안전하게 수행한다.
3. Image OCR, 문자 Chunk, Polling, Gemini Embedding, `document_chunks` Repository는 기존 구현을 재사용한다.
4. 임베딩 모델 선정·RAG 연결·`chunk_embeddings`는 수정하지 않는다.
5. Admin Vector 저장과 실제 상담 RAG 검색의 현재 분리를 구현 완료 보고에서 명확히 밝힌다.
