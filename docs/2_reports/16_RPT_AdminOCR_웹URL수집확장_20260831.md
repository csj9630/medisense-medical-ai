# Admin OCR 웹 URL 수집 확장 작업 완료 보고서

- 작업일: 2026-08-31
- 기준 지시서: `docs/1_prompts/11_PRM_AdminOCR_웹URL수집확장지시서_20260831.md`
- 작업 영역: Admin Frontend / FastAPI / AI OCR Core / Test
- 핵심 범위: 파일 업로드와 웹 URL 입력 분리, 웹 본문 추출, 내부 이미지 OCR, 기존 Chunk·VectorDB 저장 흐름 재사용
- 고정 사항: Gemini `gemini-embedding-001`, 1024차원 Vector, `document_chunks` 저장 구조 유지
- 제외 사항: RAG Embedding Provider 연결, `chunk_embeddings`, DB Migration, Vector Schema 변경

---

## 1. 최종 구현 결과

Admin OCR 탭의 입력부를 다음 두 소스로 분리했다.

```text
파일 업로드
  → 기존 POST /api/admin/ocr/jobs
  → 기존 File OCR

웹페이지 URL
  → POST /api/admin/ocr/url-jobs
  → URL/DNS/Redirect 보안 검증
  → HTML 본문 직접 추출
  → 내부 이미지 다운로드 및 PaddleOCR

두 흐름 공통
  → OcrDocumentResponse
  → 기존 문자 단위 Chunk 생성
  → 기존 Job 상태 조회
  → 기존 POST /api/admin/ocr/vector-save
  → 기존 Gemini Embedding
  → 기존 document_chunks.embedding VECTOR(1024)
```

파일과 URL은 입력 단계만 다르며, 분석 결과 표시부터 Chunk 검토와 VectorDB 저장까지는 같은 UI와 Backend 계약을 사용한다.

---

## 2. Frontend 변경

### 2.1 입력 방식 분리

OCR 입력 카드 상단에 `파일 업로드`와 `웹페이지 URL` 세그먼트 선택기를 추가했다.

- 선택을 바꾸면 진행 중 요청을 취소하고 이전 분석·저장 상태를 초기화한다.
- 파일 모드에서는 기존 Dropzone, 선택 파일, PDF/Image 미리보기를 그대로 사용한다.
- URL 모드에서는 URL 입력, 미리보기, 새 창 원문 확인 기능을 제공한다.
- Chunk Size와 Overlap 설정, 분석 결과, 저장 버튼은 두 모드가 공유한다.

### 2.2 URL 미리보기

- 사용자가 `미리보기`를 눌렀을 때만 `iframe`을 생성한다.
- `sandbox=""`와 `referrerPolicy="no-referrer"`를 적용했다.
- 대상 사이트의 `X-Frame-Options` 또는 CSP로 표시가 차단될 수 있으므로 새 창 링크를 함께 제공한다.
- 미리보기 성공 여부와 Backend 수집 가능 여부는 별개다. 실제 수집은 Backend의 보안 검증을 통과해야 한다.

### 2.3 결과 계약

기존 OCR 결과에 하위 호환 기본값을 가진 다음 필드만 추가했다.

| 필드 | 값 | 용도 |
|---|---|---|
| `sourceType` | `file` 또는 `url` | 입력 출처 구분 |
| `sourceUrl` | 최종 URL 또는 `null` | URL 원문 링크 및 저장 출처 |

웹 결과 화면에는 최종 원문 URL 링크를 표시한다. 중복된 Chunk 텍스트가 React Key 충돌을 만들지 않도록 Chunk Index도 Key에 포함했다.

---

## 3. Backend 및 AI OCR 변경

### 3.1 URL Job API

신규 API:

```http
POST /api/admin/ocr/url-jobs
Authorization: Bearer <admin JWT>
Content-Type: application/json

{
  "url": "https://example.com/article",
  "chunkSize": 512,
  "overlap": 50
}
```

응답은 파일 Job과 같은 `202 Accepted` 및 `OcrJobCreatedResponse`다. 이후 상태 조회는 기존 `GET /api/admin/ocr/jobs/{jobId}`를 사용한다. 신규 URL 생성 Endpoint에는 Backend `require_admin` 검사를 적용했고 Frontend는 저장된 관리자 JWT를 전달한다.

### 3.2 웹 수집 보안

`WebDocumentFetcher`에 다음 보호 장치를 적용했다.

- `http`, `https` Scheme만 허용
- URL 사용자명·비밀번호 거부
- 기본 포트 80·443만 허용
- URL 길이 제한 및 Fragment 제거
- 요청과 모든 Redirect 단계에서 DNS 재검증
- Loopback, Private, Link-local, Reserved 등 비공개 IP 거부
- 검증한 공개 IP로 실제 연결을 고정하고 원래 Host/SNI를 유지해 DNS Rebinding 창을 축소
- HTTPS에서 HTTP로 내려가는 페이지 Redirect 거부
- 환경 Proxy 무시(`trust_env=False`)
- HTML, 개별 이미지, 이미지 합계에 Streaming Byte 제한 적용
- Connect/Read Timeout, Redirect 횟수, 이미지 개수·동시성 제한
- JPEG, PNG, WebP만 허용하고 실제 Image Format·크기·Pixel 수 재검증

하나의 내부 이미지가 실패해도 문서 전체를 실패시키지 않고 결과 `notes`에 경고를 남긴다.

### 3.3 HTML 및 이미지 OCR

네트워크 수집과 HTML/OCR Core를 분리했다.

- `lxml`로 `main`/`article` 우선 본문을 추출한다.
- Heading, Paragraph, List, Blockquote, Pre, Table을 DOM 순서대로 정리한다.
- Script, Style, Nav, Footer, Form, Iframe 등 RAG 노이즈 영역은 제외한다.
- 상대 이미지 URL과 Lazy-load 속성을 절대 URL로 변환하고 중복을 제거한다.
- 다운로드한 내부 이미지는 기존 `preprocess_image`와 공유 PaddleOCR Service를 사용한다.
- 이미지 OCR 텍스트는 `## 웹페이지 이미지 OCR: <label>` 구역으로 HTML 본문 뒤에 병합한다.
- 최종 텍스트는 기존 `clean_document_text`와 `create_chunks`를 사용한다.

JavaScript 실행이 필요한 SPA의 렌더링 결과는 이번 범위에 포함하지 않았다. 서버가 내려준 HTML에 본문이 없는 페이지는 분석 실패로 반환한다.

---

## 4. Gemini 및 Neon 영향 범위

### 4.1 변경하지 않은 항목

- `EmbeddingService`와 Gemini Provider
- `EMBEDDING_PROVIDER=gemini`
- `EMBEDDING_MODEL=gemini-embedding-001`
- `EMBEDDING_DIMENSION=1024`
- `DocumentRepository.save_with_chunks`
- `document_chunks.embedding VECTOR(1024)`
- DB Model, Alembic Migration, Neon Schema
- `ai/rag` Provider와 검색 흐름

### 4.2 저장 시 유일한 출처 분기

파일 Job은 기존처럼 다음 값을 저장한다.

```text
ocr-job://<job-id>/<file-name>
```

URL Job은 수집 과정에서 Redirect 검증을 끝낸 최종 URL을 `original_file_url`에 저장한다.

Chunk 목록은 URL 분석 Job에 이미 저장된 기존 `OcrDocumentResponse.chunks`를 그대로 Gemini에 전달한다. 따라서 URL 확장 때문에 Embedding Model이나 Neon Transaction 동작은 달라지지 않는다.

---

## 5. 운영 설정

`.env.example`에 다음 제한을 추가했다.

```dotenv
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

텍스트와 Chunk 상한은 과도한 Gemini 호출량과 Neon 저장량도 함께 제한한다.

---

## 6. 테스트 추가 범위

- URL Scheme, Credentials, Custom Port 거부
- Private DNS 결과 차단
- 검증된 IP로 연결 고정 및 원본 Host 유지
- Redirect 후 최종 URL 유지
- HTML Streaming 크기 제한
- 내부 이미지 전체 Byte Budget
- HTML 본문·Heading·이미지 URL 추출
- 내부 이미지 OCR 텍스트 병합
- URL과 파일의 공통 Job 상태 계약
- 신규 Endpoint 관리자 인증 및 camelCase 계약
- URL Job의 기존 Gemini Chunk 입력 재사용
- URL Job의 최종 URL 저장
- Frontend TypeScript 및 Production Build

---

## 7. 변경 파일

### AI OCR Core

- `ai/ocr/errors.py`
- `ai/ocr/extractors/web.py`

### Backend

- `backend/app/api/admin/router.py`
- `backend/app/core/config.py`
- `backend/app/schemas/admin.py`
- `backend/app/services/admin_ocr.py`
- `backend/app/services/ocr_job_service.py`
- `backend/app/services/ocr_workflow.py`
- `backend/app/services/web_document_fetcher.py`
- `backend/app/services/web_ocr_workflow.py`
- `backend/tests/test_admin_ocr_api.py`
- `backend/tests/test_ocr_jobs.py`
- `backend/tests/test_ocr_vector_save.py`
- `backend/tests/test_web_ocr.py`

### Frontend

- `frontend/src/features/admin/admin.css`
- `frontend/src/features/admin/components/ocr/OcrPanel.tsx`
- `frontend/src/features/admin/components/ocr/OcrResultSummary.tsx`
- `frontend/src/features/admin/components/ocr/OcrSourceSelector.tsx`
- `frontend/src/features/admin/components/ocr/OcrWebUrlInput.tsx`
- `frontend/src/features/admin/hooks/useOcrTest.ts`
- `frontend/src/features/admin/mocks/ocrMockData.ts`
- `frontend/src/features/admin/services/apiAdminAiService.ts`
- `frontend/src/features/admin/types/ocr.ts`

### 환경 및 문서

- `.env.example`
- `docs/2_reports/16_RPT_AdminOCR_웹URL수집확장_20260831.md`

---

## 8. 검증 결과

최종 검증 명령과 결과는 작업 종료 시점 기준으로 기록한다.

| 검증 | 결과 |
|---|---|
| Python Compile | 성공 |
| Backend `unittest` 전체 | 성공 |
| Web OCR 단위 테스트 | 성공 |
| Frontend `tsc --noEmit` | 성공 |
| Frontend Vite Production Build | 성공 |
| `git diff --check` | 성공 |

별도 `pytest tests/ai/ocr` 명령은 Backend 가상환경에 `pytest`가 설치되어 있지 않아 실행하지 못했다. 대신 신규 Web OCR 검증을 프로젝트의 설치된 `unittest` Discovery에 포함했다.

외부 사이트를 대상으로 한 Live E2E는 실행 환경의 네트워크 및 사이트별 정책에 영향을 받으므로 이번 자동 검증에서는 제외했다. HTTP 수집 테스트는 `httpx.MockTransport`와 주입 DNS Resolver를 사용해 Redirect, DNS Pinning, 크기 제한을 재현했다.

---

## 9. 후속 고려 사항

이번 작업 범위 밖이지만 운영 전 다음 사항을 별도 협의할 수 있다.

- 여러 Uvicorn Worker/Instance 간 Job 상태 공유가 필요하면 메모리 Job을 외부 Queue/Store로 이전
- JavaScript 렌더링 SPA 지원이 필요하면 별도 격리 Browser Worker 도입
- 사이트별 Robots/이용약관/수집 정책 운영 기준 확정
- 기존 파일 Job 상태 조회와 Vector Save Endpoint의 Backend 관리자 인증 일괄 적용
- Gemini 무료 사용량 한도와 Embedding Provider 교체 정책 확정

현재 구현은 요청 범위에 따라 Embedding 협업 영역을 변경하지 않은 채 URL 입력과 OCR 수집 기능만 확장했다.

---

## 10. 질병관리청 상세 페이지 회귀 보완

2026-08-31 실제 질병관리청 건강정보 상세 URL을 입력했을 때 본문 대신 다음 분류 필터만 추출되는 문제를 재현했다.

```text
주제별 전체 건강문제 치료방법 검사방법 생활습관 관리 ...
```

원인은 두 가지였다.

1. `<main>`이 없는 페이지에서 첫 번째 `<article>`을 선택했으나, 해당 요소는 실제 본문이 아닌 `src-subject-wrap` 분류 필터였다.
2. 실제 상세 본문 전체가 `<form>` 안에 있었는데, 기존 노이즈 제거가 Form과 자식 콘텐츠를 함께 삭제했다.

다음과 같이 보완했다.

- Form Element는 제거하되 자식 본문은 보존하도록 `drop_tag()` 적용
- `main/article` 첫 항목 고정 선택 제거
- 본문 후보의 Heading·Paragraph·List·Table Text 양, 전체 Text 길이, Link 비율, Form Control 수를 점수화
- `data-content`, `print-content`, `article-body` 등 본문 Marker 가점
- `filter`, `menu`, `search`, `subject-wrap`, `sidebar` 등 탐색 영역 감점
- 분류 Article과 Form 내부 본문을 재현하는 회귀 Test 추가

실제 대상 URL의 HTML 추출 단계 재검증 결과:

| 항목 | 수정 전 | 수정 후 |
|---|---:|---:|
| 추출 Text | 78자 | 7,641자 |
| 내부 Image 후보 | 0개 | 8개(장식 배지 제외) |
| 본문 제목 `고혈압` | 누락 | 포함 |
| 정의·원인·진단·치료 Section | 누락 | 포함 |

실페이지 검증은 아래 페이지 응답 HTML을 신규 Fetcher와 Parser에 통과시키는 방식으로 수행했다.

- `https://health.kdca.go.kr/healthinfo/biz/health/gnrlzHealthInfo/gnrlzHealthInfo/gnrlzHealthInfoView.do?cntnts_sn=6765`

---

## 11. 잘못된 이미지 MIME 및 장식 이미지 보완

질병관리청 두통 상세 페이지에서 콘텐츠 이미지 4개 중 실제 OCR된 것은 없고, 공공누리 배지만 OCR되는 문제를 재현했다.

조사 결과 콘텐츠 이미지 다운로드 Endpoint가 정상 JPEG Byte를 반환하면서 HTTP Header를 다음처럼 제공했다.

```text
Content-Type: doesn/matter
```

기존 Fetcher가 HTTP MIME Allowlist를 먼저 적용해 정상 JPEG 4개를 모두 거부한 것이 원인이었다. 반면 공공누리 배지는 정상 `image/png` Header를 사용해 통과했다.

다음과 같이 보완했다.

- 이미지 HTTP `Content-Type`을 최종 판정 기준에서 제외
- Streaming Byte 한도는 기존대로 유지
- Pillow Decode와 실제 File Signature로 JPEG·PNG·WebP 여부 검증
- 실제 이미지가 아니거나 지원하지 않는 Format이면 기존처럼 거부
- `license`, `copyright`, `badge`, `logo`, `icon`, `open-box` Marker의 장식 이미지는 OCR 후보에서 제외
- 실패 경고에 이미지 순번을 포함해 Alt Text가 같은 이미지도 개별 식별
- 잘못된 MIME의 정상 JPEG 허용 및 장식 배지 제외 회귀 Test 추가

실제 대상 URL 재검증 결과:

| 항목 | 수정 전 | 수정 후 |
|---|---:|---:|
| 콘텐츠 이미지 후보 | 4개 | 4개 |
| 다운로드 성공 | 0개 | 4개 |
| MIME 관련 경고 | 3줄(중복 Alt 경고 병합) | 0개 |
| 공공누리 배지 OCR 후보 | 포함 | 제외 |

- `https://health.kdca.go.kr/healthinfo/biz/health/gnrlzHealthInfo/gnrlzHealthInfo/gnrlzHealthInfoView.do?cntnts_sn=5830`
