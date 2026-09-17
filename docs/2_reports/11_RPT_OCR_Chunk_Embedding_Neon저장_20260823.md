# OCR Chunk Embedding 및 Neon 저장 기능 구현 결과 보고서

- 작업일: 2026-08-23
- 작업 영역: Frontend / FastAPI Backend / PostgreSQL / Neon / pgvector
- 대상 기능: 관리자 OCR 결과의 Chunk Embedding 생성 및 VectorDB 저장
- 주요 기술: React, TypeScript, FastAPI, SQLAlchemy, PostgreSQL, Neon, pgvector, Google GenAI
- 작업 범위: 완료된 OCR Job 조회, 기존 Chunk 임베딩, `VECTOR(1024)` 검증, 문서·Chunk Transaction 저장, 저장 API와 UI 연결, 오류 처리와 테스트
- 제외 범위: Vector 검색 API, RAG 검색, HNSW·IVFFlat 인덱스, Queue, 재시도 시스템, 원본 파일 저장소, 관리자 인증·RLS 변경

## 1. 작업 목적

기존 관리자 OCR 기능은 실제 파일을 읽어 다음 단계까지 처리하고 있었다.

```text
파일 업로드 → OCR/직접 추출 → 텍스트 정제 → Chunk 생성 → 화면 표시
```

그러나 화면의 `VectorDB 저장 테스트` 버튼은 문서 이름만 Mock API에 보내고 고정 성공 메시지를 받았다. 실제 Embedding 생성과 DB 저장은 수행하지 않았다.

이번 작업의 목적은 OCR 내부 구조를 다시 만들지 않고, 이미 만들어진 Chunk를 그대로 사용해 다음 흐름을 완성하는 것이다.

```text
기존 OCR Chunk
→ Gemini Embedding
→ 1024차원 Vector 검증
→ Neon PostgreSQL 문서 저장
→ Neon PostgreSQL Chunk + Vector 저장
```

이번 결과는 Mock이 아니다. Gemini Embedding API와 Neon PostgreSQL을 실제로 호출하는 구현이다.

## 2. 작업 전과 작업 후

### 2.1 작업 전

```text
사용자 저장 버튼 클릭
→ Frontend가 documentName 전송
→ POST /api/admin/ocr/vector-save-test
→ Backend Mock Service
→ 실제 DB 변경 없이 성공 문구 반환
```

문제점은 다음과 같았다.

- OCR Chunk가 저장 요청에 연결되지 않았다.
- Embedding 모델이 호출되지 않았다.
- `admin_documents`와 `document_chunks`에 실제 행이 생기지 않았다.
- API 성공이 실제 저장 성공을 의미하지 않았다.

### 2.2 작업 후

```text
사용자 저장 버튼 클릭
→ Frontend가 완료된 OCR jobId 전송
→ POST /api/admin/ocr/vector-save
→ Backend가 메모리 OCR Job에서 기존 Chunk 조회
→ Gemini가 Chunk별 1024차원 Vector 생성
→ Chunk 수와 Vector 수·차원 검증
→ admin_documents INSERT
→ 생성된 document_id 확보
→ document_chunks 일괄 INSERT
→ Commit
→ 실제 documentId와 저장 Chunk 수 반환
```

Frontend가 Chunk 전체를 다시 보내지 않는 이유는 Backend OCR Job에 최종 OCR 결과와 Chunk가 이미 있기 때문이다. `jobId`만 보내면 같은 Chunk를 다시 조회할 수 있어 Request 크기와 데이터 중복을 줄일 수 있다.

## 3. 전체 실행 흐름

### 3.1 OCR부터 저장까지

```text
1. 파일 선택
   ↓
2. POST /api/admin/ocr/jobs
   ↓
3. OcrJobManager가 OCR 실행
   ↓
4. 텍스트 정제 및 기존 create_chunks() 실행
   ↓
5. Frontend가 GET /api/admin/ocr/jobs/{jobId}로 완료 결과 조회
   ↓
6. Frontend가 결과와 jobId를 함께 보관
   ↓
7. 사용자가 "VectorDB에 저장" 클릭
   ↓
8. POST /api/admin/ocr/vector-save { "jobId": "..." }
   ↓
9. save_ocr_result_with_embeddings()
   ├─ OcrJobManager.get_job()
   │  ← 완료 상태, 추출 텍스트, 기존 Chunk 반환
   ├─ GeminiEmbeddingService.embed_chunks()
   │  ← Chunk 순서와 같은 1024차원 Vector 목록 반환
   └─ DocumentRepository.save_with_chunks()
      ← documentId, 저장 Chunk 수 반환
   ↓
10. Frontend에 저장 성공 또는 실패 표시
```

### 3.2 중심 함수

전체 저장 순서를 관리하는 중심 함수는 다음 함수다.

```python
save_ocr_result_with_embeddings()
```

위치:

```text
backend/app/services/admin_ocr.py
```

이 함수는 직접 SQL을 작성하거나 Gemini SDK 세부사항을 처리하지 않는다. 각 역할을 전문 모듈에 맡기고 결과를 다시 받아 다음 단계로 전달한다.

```text
save_ocr_result_with_embeddings()

→ job_manager.get_job(jobId)
← OcrJobStatusResponse

→ embedder.embed_chunks(chunks)
← list[list[float]]

→ repository.save_with_chunks(...)
← SavedDocument

→ OcrVectorSaveResponse 조립
```

처음 코드를 읽는다면 이 함수를 기준으로 호출되는 파일을 따라가는 것이 가장 쉽다.

## 4. 파일별 역할

| 파일 | 상태 | 역할 |
| --- | --- | --- |
| `backend/app/api/admin/router.py` | 수정 | 실제 저장 Endpoint와 HTTP 오류 변환 |
| `backend/app/schemas/admin.py` | 수정 | `jobId` Request 및 저장 결과 Response 정의 |
| `backend/app/services/admin_ocr.py` | 수정 | OCR Job 조회부터 Embedding·DB 저장까지 전체 순서 관리 |
| `backend/app/services/embedding_service.py` | 추가 | Gemini 배치 Embedding 호출과 결과 검증 |
| `backend/app/repositories/document_repository.py` | 추가 | 문서와 Chunk를 하나의 Transaction으로 저장 |
| `backend/app/core/config.py` | 수정 | Embedding 모델·차원·Timeout 환경설정 |
| `frontend/src/features/admin/types/ocr.ts` | 수정 | Frontend 저장 Request/Response 타입과 `jobId` 보관 |
| `frontend/src/features/admin/services/apiAdminAiService.ts` | 수정 | 실제 `/ocr/vector-save` API 호출 |
| `frontend/src/features/admin/hooks/useOcrTest.ts` | 수정 | 저장 버튼에서 완료된 `jobId` 전달 |
| `frontend/src/features/admin/components/ocr/OcrResultSummary.tsx` | 수정 | Mock 표현을 실제 VectorDB 저장 표현으로 변경 |
| `backend/tests/test_ocr_vector_save.py` | 추가 | Embedding, Transaction, 중심 흐름, HTTP 오류 검증 |
| `.env.example` | 수정 | Embedding 환경변수 예시 추가 |
| `README.md` | 수정 | 실제 OCR→Embedding→Neon 흐름과 설정 반영 |

## 5. API Request와 Response

### 5.1 Endpoint

```text
POST /api/admin/ocr/vector-save
Content-Type: application/json
```

### 5.2 Request

```json
{
  "jobId": "완료된 OCR Job ID"
}
```

| 필드 | 의미 |
| --- | --- |
| `jobId` | Backend 메모리에 보관된 OCR 완료 결과를 찾는 ID |

`documentName`, 전체 OCR 텍스트, Chunk 배열은 Frontend가 다시 보내지 않는다.

### 5.3 성공 Response 예시

```json
{
  "message": "OCR 문서와 Chunk 12개를 VectorDB에 저장했습니다.",
  "documentId": "문서 UUID",
  "chunkCount": 12,
  "embeddingDimension": 1024,
  "embeddingModel": "gemini-embedding-001"
}
```

| 필드 | 의미 |
| --- | --- |
| `documentId` | `vector_db.admin_documents.id`에 생성된 UUID |
| `chunkCount` | `vector_db.document_chunks`에 저장된 행 개수 |
| `embeddingDimension` | 각 Vector의 차원 수. 현재 DB 계약과 같은 1024 |
| `embeddingModel` | 실제 사용한 Embedding 모델명 |

`documentId`는 Neon SQL Editor에서 방금 저장한 문서와 Chunk를 정확히 찾을 때 사용할 수 있다.

## 6. Embedding 처리 상세

### 6.1 설정

```dotenv
GEMINI_API_KEY=
EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIMENSION=1024
EMBEDDING_TIMEOUT_SECONDS=60
```

실제 API Key는 최상위 `.env`에만 저장한다. 코드, Git, 문서, Frontend 환경변수에는 기록하지 않는다.

### 6.2 호출 구조

`GeminiEmbeddingService.embed_chunks()`는 Chunk 목록 전체를 Google GenAI SDK의 비동기 `embed_content`에 전달한다.

```python
config={
    "task_type": "RETRIEVAL_DOCUMENT",
    "output_dimensionality": 1024,
}
```

`RETRIEVAL_DOCUMENT`는 저장할 문서 조각을 Embedding한다는 용도를 Provider에 알려준다. `output_dimensionality`는 DB의 `VECTOR(1024)`와 맞추기 위해 1024로 고정한다.

### 6.3 저장 전 검증

DB INSERT 전에 다음 조건을 검사한다.

- Chunk 목록이 비어 있지 않은가
- 공백뿐인 Chunk가 없는가
- 설정 차원이 정확히 1024인가
- 입력 Chunk 수와 반환 Vector 수가 같은가
- 모든 Vector 길이가 정확히 1024인가
- Vector 값이 숫자로 변환 가능한가
- `NaN`, 양의 무한대, 음의 무한대가 없는가

하나라도 실패하면 Repository를 호출하지 않으므로 DB에 문서만 먼저 생기는 일이 없다.

### 6.4 Chunk 순서 유지

Embedding 결과는 입력 순서를 그대로 유지한다.

```text
chunks[0] → embeddings[0] → chunk_index 0
chunks[1] → embeddings[1] → chunk_index 1
chunks[2] → embeddings[2] → chunk_index 2
```

이 순서가 유지되어야 나중에 문서를 원래 순서대로 재구성할 수 있다.

## 7. PostgreSQL과 Neon 이해하기

### 7.1 PostgreSQL과 Neon의 관계

PostgreSQL은 관계형 데이터베이스 엔진이다. 테이블, 행, 기본키, 외래키, Transaction 같은 데이터 규칙과 SQL 실행을 담당한다.

Neon은 PostgreSQL과 전혀 다른 DB 문법을 쓰는 별도 제품이 아니라, PostgreSQL을 클라우드에서 사용할 수 있게 제공하는 서비스다. 이 프로젝트는 SQLAlchemy와 `psycopg`로 Neon에 연결하지만 실제로 실행되는 SQL과 테이블 규칙은 PostgreSQL 규칙이다.

```text
FastAPI
→ SQLAlchemy ORM
→ psycopg PostgreSQL Driver
→ 암호화된 DATABASE_URL 연결
→ Neon의 PostgreSQL
```

Neon의 Project 안에는 branch, database, role, compute가 있다.

- Project: 관련 Neon 자원을 담는 최상위 단위
- Branch: 데이터베이스의 격리된 분기. 같은 프로젝트여도 branch가 다르면 데이터가 다를 수 있음
- Database: SQL 테이블이 실제로 속한 데이터베이스
- Role: DB 접속 권한을 가진 PostgreSQL 사용자
- Compute: SQL을 실행하는 PostgreSQL 연산 자원

따라서 “저장은 성공했는데 Neon 웹에서 행이 안 보인다”면 코드보다 먼저 웹 Console과 `.env`가 같은 Project의 같은 branch/database를 보고 있는지 확인해야 한다.

### 7.2 이 프로젝트의 schema

PostgreSQL의 schema는 같은 database 안에서 테이블 이름을 구분하는 폴더 같은 namespace다.

이 프로젝트에는 주요 schema가 두 개 있다.

```text
app_db
└─ users 등 일반 애플리케이션 테이블

vector_db
├─ admin_documents
└─ document_chunks
```

SQL에서 `vector_db.admin_documents`라고 쓰는 이유는 `vector_db` schema 안의 `admin_documents` 테이블을 명확하게 선택하기 위해서다.

### 7.3 문서와 Chunk의 1:N 관계

```text
vector_db.admin_documents
id = A
        │
        ├─ vector_db.document_chunks.document_id = A, chunk_index = 0
        ├─ vector_db.document_chunks.document_id = A, chunk_index = 1
        └─ vector_db.document_chunks.document_id = A, chunk_index = 2
```

문서 한 개가 여러 Chunk를 가지므로 1:N 관계다.

`admin_documents.id`는 UUID 기본키다. `document_chunks.document_id`는 이 UUID를 참조하는 외래키다. DB 스키마에는 `ON DELETE CASCADE`가 설정되어 있어 문서 행을 삭제하면 연결된 Chunk도 함께 삭제된다. 삭제는 복구가 어려울 수 있으므로 Neon SQL Editor에서 `DELETE`를 시험 명령처럼 실행하면 안 된다.

### 7.4 실제 저장 컬럼

#### `vector_db.admin_documents`

| 컬럼 | 저장 내용 | 비고 |
| --- | --- | --- |
| `id` | DB가 생성한 UUID | 문서 기본키 |
| `original_file_url` | 현재 `ocr-job://...` 추적 참조값 | 실제 다운로드 URL이 아님 |
| `uploaded_by` | 현재 `NULL` 가능 | 이번 작업에서 관리자 인증을 연결하지 않음 |
| `ocr_extracted_text` | 정제된 전체 OCR 텍스트 | Chunk 전 원문 |
| `ocr_status` | `completed` | 현재 저장 완료 표시 |
| `created_at` | DB 생성 시각 | PostgreSQL `now()` 기본값 |

#### `vector_db.document_chunks`

| 컬럼 | 저장 내용 | 비고 |
| --- | --- | --- |
| `id` | DB가 생성한 UUID | Chunk 기본키 |
| `document_id` | 부모 문서 UUID | `admin_documents.id` 외래키 |
| `chunk_index` | `0, 1, 2, ...` | 원래 Chunk 순서 |
| `chunk_text` | OCR Chunk 문자열 | Embedding 입력과 같은 텍스트 |
| `embedding` | 1024개 실수로 된 Vector | `VECTOR(1024)` |
| `created_at` | DB 생성 시각 | PostgreSQL `now()` 기본값 |

### 7.5 pgvector와 `VECTOR(1024)`

일반 PostgreSQL에는 텍스트와 숫자 같은 기본 타입이 있지만 AI Embedding 전용 Vector 타입은 기본 타입이 아니다. `pgvector` 확장이 PostgreSQL에 Vector 타입과 거리 연산자를 추가한다.

Neon은 `pgvector`를 지원하며, 공식 문서도 Neon SQL Editor 또는 연결된 SQL Client에서 `CREATE EXTENSION vector;`로 활성화할 수 있다고 설명한다. 현재 프로젝트 DB에는 이미 Vector 컬럼과 Python `pgvector` 타입 연결이 존재하므로 이번 작업에서 schema나 extension을 새로 만들지 않았다.

```text
Python list[float] 1024개
→ pgvector SQLAlchemy 타입
→ PostgreSQL VECTOR(1024)
```

`1024`는 한 행에 숫자 1024개가 있다는 뜻이다. Chunk가 10개라면 Vector도 10개이며, 각 Vector마다 값이 1024개다.

이번 범위에서는 Vector를 저장만 한다. `<->`, `<=>` 같은 거리 연산자를 사용하는 유사도 검색과 HNSW·IVFFlat 인덱스는 구현하지 않았다.

## 8. Transaction이 필요한 이유

문서와 Chunk는 서로 떨어진 두 테이블에 저장되지만 하나의 논리적 작업이다.

Transaction이 없다면 다음 문제가 생길 수 있다.

```text
admin_documents INSERT 성공
→ Chunk 0 INSERT 성공
→ Chunk 1 INSERT 중 오류
→ 문서와 일부 Chunk만 남음
```

현재 Repository는 다음 순서로 처리한다.

```text
1. AdminDocuments 객체 추가
2. flush()
3. DB가 생성한 document.id 확보
4. 같은 document.id를 가진 DocumentChunks 객체 전체 생성
5. add_all()
6. commit()
```

`flush()`는 SQL을 DB에 보내 UUID를 얻지만 Transaction을 최종 확정하지는 않는다. 따라서 이후 Chunk 저장에 실패하면 아직 전체 작업을 되돌릴 수 있다.

성공 시:

```text
commit() → 문서와 모든 Chunk 확정
```

실패 시:

```text
rollback() → 해당 Transaction의 문서와 Chunk 변경 전체 취소
```

이것이 “문서만 저장되고 Chunk 일부가 누락되는 상태”를 방지하는 핵심이다.

## 9. `original_file_url` 처리

현재 DB 모델에서 `admin_documents.original_file_url`은 `NOT NULL`이다. 그러나 OCR Job은 업로드 파일을 메모리에서 처리하며 R2/S3에 영구 원본 URL을 만들지 않는다.

이번 작업에서는 DB 컬럼을 임의로 nullable로 바꾸거나 새 파일 저장소를 만들지 않고 다음 추적 참조값을 저장한다.

```text
ocr-job://{jobId}/{URL 인코딩된 파일명}
```

이 값은 실제 웹 주소가 아니다. 브라우저로 열거나 원본 파일을 다운로드할 수 없다. `https://` URL과 구분되는 scheme을 사용해 영구 보관 파일처럼 오해하지 않도록 했다.

파일명이 길어 500자 컬럼 제한을 넘으면 파일명 SHA-256 digest를 사용한 짧은 참조값으로 대체한다.

원본 파일 다운로드가 필요해지는 후속 단계에서는 R2/S3 등 실제 저장소에 먼저 파일을 보관하고 이 컬럼을 실제 URL 또는 Object Key 정책에 맞게 교체해야 한다.

## 10. Neon 웹 Console에서 저장 결과 확인하기

Neon Console 화면은 업데이트될 수 있지만, 2026-08-23 기준 공식 문서에서 확인되는 기본 진입점은 Project의 왼쪽 메뉴 `SQL Editor`다. `Tables` 페이지에서도 데이터를 볼 수 있지만 schema·관계·Vector 차원을 함께 확인하기에는 SQL Editor가 더 명확하다.

### 10.1 올바른 Project, branch, database 선택

1. [Neon Console](https://console.neon.tech/)에 로그인한다.
2. 이 프로젝트가 사용하는 Neon Project를 연다.
3. Project Dashboard에서 `Connect`를 눌러 branch, database, role을 확인한다.
4. 프로젝트 최상위 `.env`의 `DATABASE_URL`이 가리키는 대상과 같은지 확인한다.
5. 왼쪽 메뉴에서 `SQL Editor`를 연다.
6. SQL Editor 상단의 branch와 database 선택값이 `DATABASE_URL`과 같은지 다시 확인한다.

주의: 문서에 실제 `DATABASE_URL`, 비밀번호, role 암호를 붙여 넣지 않는다. Neon 공식 문서에 따르면 Dashboard의 `Connect` 버튼에서 branch·role·database를 선택하면 연결 문자열이 만들어진다.

### 10.2 현재 접속 위치 확인

SQL Editor에서 다음 Query를 실행한다.

```sql
SELECT
    current_database() AS database_name,
    current_user AS role_name,
    current_schema() AS current_schema;
```

여기서 `database_name`이 `.env` 연결 대상과 다르면 다른 database를 보고 있는 것이다.

### 10.3 `pgvector` 활성화 확인

```sql
SELECT extname, extversion
FROM pg_extension
WHERE extname = 'vector';
```

정상이라면 `vector` 행과 설치 버전이 표시된다. 행이 없다면 현재 선택한 database가 잘못되었거나 extension 설치가 누락된 것이다.

이번 프로젝트의 테이블과 컬럼이 이미 존재하는 DB에서는 임의로 `CREATE EXTENSION`이나 `CREATE TABLE`을 다시 실행하지 않는다. 먼저 팀의 schema 관리 방식을 확인한다.

### 10.4 테이블 존재 확인

```sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'vector_db'
  AND table_name IN ('admin_documents', 'document_chunks')
ORDER BY table_name;
```

정상 결과:

```text
vector_db | admin_documents
vector_db | document_chunks
```

### 10.5 최신 문서 저장 행 확인

Admin 화면에서 OCR 저장을 성공시킨 직후 다음 Query를 실행한다.

```sql
SELECT
    id,
    original_file_url,
    ocr_status,
    length(ocr_extracted_text) AS extracted_character_count,
    created_at
FROM vector_db.admin_documents
ORDER BY created_at DESC
LIMIT 20;
```

확인할 항목:

- 성공 Response의 `documentId`와 `id`가 같은가
- `original_file_url`이 `ocr-job://`로 시작하는가
- `ocr_status`가 `completed`인가
- `extracted_character_count`가 0보다 큰가
- `created_at`이 방금 저장한 시각인가

### 10.6 문서별 Chunk 수와 Vector 상태 확인

```sql
SELECT
    d.id AS document_id,
    d.created_at,
    COUNT(c.id) AS chunk_count,
    COUNT(c.embedding) AS embedded_chunk_count,
    MIN(c.chunk_index) AS first_chunk_index,
    MAX(c.chunk_index) AS last_chunk_index,
    MIN(vector_dims(c.embedding)) AS min_dimension,
    MAX(vector_dims(c.embedding)) AS max_dimension
FROM vector_db.admin_documents AS d
LEFT JOIN vector_db.document_chunks AS c
       ON c.document_id = d.id
GROUP BY d.id, d.created_at
ORDER BY d.created_at DESC
LIMIT 20;
```

Chunk가 12개인 정상 예시:

```text
chunk_count          = 12
embedded_chunk_count = 12
first_chunk_index    = 0
last_chunk_index     = 11
min_dimension        = 1024
max_dimension        = 1024
```

`chunk_count`와 `embedded_chunk_count`가 다르면 Embedding이 `NULL`인 Chunk가 있다는 뜻이다. 현재 구현은 모든 Vector가 검증된 뒤 같은 Transaction으로 저장하므로 정상 저장에서는 두 값이 같아야 한다.

### 10.7 특정 문서의 Chunk 순서와 내용 확인

저장 API가 반환한 `documentId`를 아래 UUID 자리에 넣는다.

```sql
SELECT
    id AS chunk_id,
    document_id,
    chunk_index,
    left(chunk_text, 200) AS chunk_preview,
    vector_dims(embedding) AS embedding_dimension,
    embedding IS NOT NULL AS has_embedding,
    created_at
FROM vector_db.document_chunks
WHERE document_id = '여기에-documentId-입력'::uuid
ORDER BY chunk_index;
```

전체 `embedding` 값을 그대로 조회하면 숫자 1024개가 표시되어 화면이 매우 길어진다. 평소에는 `vector_dims(embedding)`과 `embedding IS NOT NULL`로 저장 여부를 확인하는 편이 낫다.

### 10.8 Chunk index 누락·중복 확인

```sql
SELECT
    document_id,
    COUNT(*) AS chunk_count,
    COUNT(DISTINCT chunk_index) AS distinct_index_count,
    MIN(chunk_index) AS min_index,
    MAX(chunk_index) AS max_index
FROM vector_db.document_chunks
WHERE document_id = '여기에-documentId-입력'::uuid
GROUP BY document_id;
```

정상 조건:

```text
distinct_index_count = chunk_count
min_index = 0
max_index = chunk_count - 1
```

### 10.9 부모 문서가 없는 Chunk 확인

외래키가 정상이라면 결과가 0행이어야 한다.

```sql
SELECT c.id, c.document_id, c.chunk_index
FROM vector_db.document_chunks AS c
LEFT JOIN vector_db.admin_documents AS d
       ON d.id = c.document_id
WHERE d.id IS NULL;
```

### 10.10 Tables 화면에서 확인

SQL 대신 표 형태로 보고 싶다면 Neon Console 왼쪽의 `Tables` 페이지를 사용할 수 있다.

1. `Tables`를 연다.
2. 올바른 branch와 database인지 확인한다.
3. schema 선택에서 `vector_db`를 찾는다.
4. `admin_documents`를 열어 최신 행을 확인한다.
5. 해당 `id`를 복사한다.
6. `document_chunks`에서 같은 `document_id`를 가진 행을 확인한다.

Console 버전에 따라 필터 UI나 컬럼 표시 방법이 달라질 수 있다. 관계와 Vector 차원을 정확히 확인할 때는 위 SQL Editor Query를 기준으로 한다.

## 11. 오류 처리와 HTTP 상태

| 상황 | DB 동작 | HTTP 상태 | 사용자 메시지 성격 |
| --- | --- | ---: | --- |
| OCR Job 없음 또는 만료 | 저장 안 함 | 404 | Job을 찾을 수 없음 |
| OCR Job 처리 중 | 저장 안 함 | 409 | 완료된 Job만 저장 가능 |
| Chunk 없음 | 저장 안 함 | 409 | 저장할 Chunk 없음 |
| 빈 Chunk·개수/차원 불일치 | 저장 안 함 | 422 | Embedding 검증 실패 |
| `GEMINI_API_KEY` 없음 | 저장 안 함 | 503 | 환경설정 필요 |
| Gemini 호출 실패·Timeout | 저장 안 함 | 502 | Embedding 생성 실패 |
| Neon INSERT/Commit 실패 | Rollback | 500 | Neon 저장 실패 |

API Key, DB 비밀번호, Chunk 원문은 Provider 오류 응답이나 일반 로그에 포함하지 않는다.

## 12. Mock과 실제 기능 구분

| 기능 | 현재 상태 | 설명 |
| --- | --- | --- |
| OCR 파일 처리 | 실제 | PDF·이미지·DOCX·PPTX 처리 |
| Chunk 생성 | 실제 | 기존 `create_chunks()` 결과 사용 |
| 저장 버튼 API | 실제 | `/api/admin/ocr/vector-save` 호출 |
| Embedding | 실제 | Gemini `gemini-embedding-001` 호출 |
| Vector 차원 | 실제 | 각 Chunk 1024차원 검증 |
| PostgreSQL 저장 | 실제 | Neon의 기존 테이블에 INSERT |
| Transaction | 실제 | Commit 또는 전체 Rollback |
| 자동 테스트 Provider | Mock 사용 | API 비용과 DB 변경 없이 실패 조건 재현 |
| 실제 통합 검증 | 실제 | Gemini와 Neon 연결 후 저장·조회 확인 |
| Vector 유사도 검색 | 미구현 | 이번 범위 제외 |
| 원본 파일 영구 보관 | 미구현 | `ocr-job://` 참조값만 저장 |

자동 테스트의 Fake Embedding과 Fake Session은 오류를 안전하게 재현하기 위한 테스트 대역이다. 운영 저장 흐름 자체가 Mock이라는 의미는 아니다.

## 13. 실행 방법

### 13.1 환경변수 확인

프로젝트 최상위 `.env`에서 변수 이름만 확인한다.

```dotenv
DATABASE_URL=Neon에서_발급한_PostgreSQL_연결문자열
GEMINI_API_KEY=개발자_API_Key
EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIMENSION=1024
EMBEDDING_TIMEOUT_SECONDS=60
```

`DATABASE_URL`의 실제 값은 공유 문서나 Git에 기록하지 않는다. Neon 연결은 SSL이 포함된 Neon 연결 문자열을 사용한다.

### 13.2 Backend 환경 준비

현재 작업 PC의 기존 `backend/.venv`는 존재하지 않는 Python 3.12 설치 경로를 가리키므로 그대로 실행되지 않는다. Python 3.12 설치 후 프로젝트 최상위에서 가상환경을 다시 만든다.

```powershell
py -3.12 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

### 13.3 서버 실행

프로젝트 최상위에서:

```powershell
.\run.bat
```

또는 개별 실행:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

```powershell
cd frontend
npm.cmd run dev
```

확인 주소:

```text
Frontend Admin: http://localhost:5173/admin
Backend Swagger: http://localhost:8000/docs
DB Health:       http://localhost:8000/health/db
```

### 13.4 화면에서 저장 확인

1. Admin 페이지의 OCR 탭을 연다.
2. 문서를 선택한다.
3. Chunk Size와 Overlap을 확인한다.
4. OCR 분석을 실행하고 완료될 때까지 기다린다.
5. Chunk 목록이 비어 있지 않은지 확인한다.
6. `VectorDB에 저장`을 클릭한다.
7. `OCR 문서와 Chunk N개를 VectorDB에 저장했습니다.` 메시지를 확인한다.
8. Browser 개발자 도구 Network에서 `/api/admin/ocr/vector-save`가 200인지 확인한다.
9. Response의 `documentId`, `chunkCount`, `embeddingDimension`을 확인한다.
10. Neon SQL Editor에서 같은 `documentId`를 조회한다.

## 14. 테스트와 실제 검증 결과

### 14.1 자동 테스트

```text
Backend unittest 전체: 55개 통과
신규 OCR Vector 저장 테스트: 14개 포함
Frontend TypeScript/Vite production build: 통과
Pyright 대상 Backend 파일: 0 errors, 0 warnings
Python compileall: 통과
git diff --check: 통과
```

테스트에서 확인한 항목:

- Chunk 2개 입력 시 Vector 2개 반환
- 입력 순서 유지
- Vector당 1024차원
- 빈 Chunk 거부
- Vector 수 불일치 거부
- Vector 차원 불일치 거부
- Provider 내부 오류 정보 비노출
- 문서와 Chunk의 동일 `document_id`
- `chunk_index` 0부터 순서대로 저장
- DB 실패 시 Rollback
- Embedding 실패 시 Repository 미호출
- API 성공 camelCase 계약
- Embedding 실패가 성공으로 응답되지 않고 502 반환
- DB 실패가 성공으로 응답되지 않고 500 반환

### 14.2 실제 Gemini·Neon 통합 검증

무해한 검증용 Chunk 1개로 실제 외부 연결을 확인했다.

```text
Gemini 실제 Embedding 생성: 성공
Embedding Dimension: 1024
Neon admin_documents INSERT: 성공
Neon document_chunks INSERT: 1개 성공
동일 document_id 관계 조회: 성공
저장된 Vector 차원 조회: 1024
검증 데이터 외부 Transaction Rollback: 성공
Rollback 후 잔여 Chunk: 없음
```

이 검증은 실제 Neon의 schema와 `VECTOR(1024)` 수용 여부까지 확인했지만, 테스트 행은 최종 Rollback되어 지금 Neon Console에는 남아 있지 않다. 실제 Admin 화면에서 저장한 문서는 Commit되므로 Console에서 조회할 수 있다.

## 15. 코드를 읽는 추천 순서

```text
1. frontend/src/features/admin/hooks/useOcrTest.ts
   저장 버튼이 어떤 값을 보내는지 확인
   ↓
2. frontend/src/features/admin/services/apiAdminAiService.ts
   /ocr/vector-save Request 확인
   ↓
3. backend/app/api/admin/router.py
   HTTP 진입점과 오류 상태 확인
   ↓
4. backend/app/schemas/admin.py
   Request/Response 필드 확인
   ↓
5. backend/app/services/admin_ocr.py
   중심 함수와 전체 실행 순서 확인
   ↓
6. backend/app/services/embedding_service.py
   Gemini 호출과 1024차원 검증 확인
   ↓
7. backend/app/repositories/document_repository.py
   flush, document_id, add_all, commit/rollback 확인
   ↓
8. backend/app/models/generated.py
   실제 schema, 컬럼, 외래키, VECTOR 타입 확인
   ↓
9. backend/tests/test_ocr_vector_save.py
   정상·실패 조건 확인
```

## 16. 결과가 보이지 않을 때 점검 순서

### 16.1 화면에는 저장 실패가 표시됨

1. Browser Network의 HTTP 상태를 확인한다.
2. 404면 OCR Job이 만료되었거나 Backend가 재시작되었는지 확인한다.
3. 409면 OCR이 완료되었고 Chunk가 존재하는지 확인한다.
4. 503이면 `GEMINI_API_KEY` 설정을 확인한다.
5. 502면 Gemini 모델명, Timeout, API 할당량과 네트워크를 확인한다.
6. 500이면 `/health/db`, Backend 로그, Neon 상태를 확인한다.

### 16.2 화면은 성공인데 Neon에 행이 안 보임

1. Response의 `documentId`를 복사한다.
2. Neon Console Project가 `.env` 대상과 같은지 확인한다.
3. SQL Editor의 branch와 database를 확인한다.
4. `vector_db` schema를 명시해 Query한다.
5. `created_at` 정렬 대신 `WHERE id = 'documentId'::uuid`로 직접 찾는다.

예:

```sql
SELECT *
FROM vector_db.admin_documents
WHERE id = '여기에-documentId-입력'::uuid;
```

### 16.3 문서는 있는데 Chunk가 없음

현재 구현에서 정상적으로 Commit된 결과라면 발생하지 않아야 한다. 다음을 확인한다.

- 조회한 `document_id`가 정확한가
- 올바른 branch/database인가
- 이전 버전 Mock 또는 수동 INSERT로 만들어진 문서인가
- Backend 로그에 `[OCR SAVE] Neon transaction rollback`이 있었는가

### 16.4 저장이 느림

저장 버튼 한 번에서 다음 두 외부 작업을 순차 수행한다.

```text
Gemini Embedding API 응답 대기
→ Neon Transaction 저장
```

별도 Background Worker가 없으므로 Chunk 수, 네트워크, Provider 응답시간, 잠자던 Neon compute의 재개 시간에 영향을 받을 수 있다.

## 17. 보안과 개인정보 주의사항

- OCR Chunk 원문은 Embedding 생성을 위해 Google Gemini API로 전송된다.
- 의료정보, 주민번호, 연락처 등 민감정보를 실제 Provider에 보내도 되는지 조직 정책을 먼저 확인해야 한다.
- `GEMINI_API_KEY`와 `DATABASE_URL`은 Backend 전용이다. `VITE_` 접두사를 붙여 Frontend에 노출하면 안 된다.
- Backend 로그에는 API Key, DB 연결 문자열, 전체 Chunk 원문을 남기지 않는다.
- Neon SQL Editor Query 결과를 공유할 때도 OCR 원문과 Vector 전체를 그대로 캡처하지 않는다.
- `uploaded_by`는 현재 nullable이며 관리자 인증 연결은 이번 범위에서 제외했다.
- 같은 Job의 저장 API를 수동으로 여러 번 호출하면 중복 문서가 생길 수 있다. UI는 성공 후 버튼을 비활성화하지만 API 수준의 idempotency key나 unique 제약은 아직 없다.
- OCR Job은 메모리에 있고 TTL이 기본 60분이므로 Backend 재시작 또는 만료 후에는 같은 `jobId`로 저장할 수 없다.

## 18. 현재 구현 상태

| 기능 | 상태 | 설명 |
| --- | --- | --- |
| 기존 OCR 결과 사용 | 구현 완료 | Backend Job의 기존 Chunk 사용 |
| Chunk Embedding | 구현 완료 | Gemini 실제 API |
| 1024차원 검증 | 구현 완료 | 개수·값·차원 검사 |
| Neon 문서 저장 | 구현 완료 | `vector_db.admin_documents` |
| Neon Chunk 저장 | 구현 완료 | `vector_db.document_chunks` |
| 문서–Chunk 관계 | 구현 완료 | UUID 외래키 사용 |
| Transaction | 구현 완료 | Commit 또는 전체 Rollback |
| Frontend 저장 연결 | 구현 완료 | `jobId` 기반 실제 API |
| Neon 웹 확인 SQL | 문서화 완료 | 문서·Chunk·Vector·관계 확인 |
| 원본 파일 영구 URL | 미구현 | `ocr-job://` 추적 참조값 사용 |
| Vector 검색 API | 미구현 | 후속 범위 |
| Vector 인덱스 | 미구현 | 후속 범위 |
| 관리자 인증·RLS | 미구현 | 후속 범위 |
| Job 영속화·Queue | 미구현 | 후속 범위 |

## 19. 후속 작업 시 주요 교체 지점

### 19.1 원본 파일 저장소 연결

현재:

```text
_build_job_file_reference()
→ ocr-job:// 추적값
```

후속:

```text
R2/S3 업로드
→ 실제 Object URL 또는 Key
→ original_file_url 저장
```

### 19.2 검색 기능 추가

현재:

```text
Chunk Embedding 저장까지만 구현
```

후속:

```text
질문 Embedding
→ pgvector 거리 연산
→ 관련 Chunk 조회
→ RAG Prompt 구성
```

검색 구현 전에는 데이터 규모와 Query 특성을 측정한 뒤 HNSW 또는 IVFFlat 필요 여부를 판단한다. 이번 작업에서는 인덱스를 만들지 않았다.

### 19.3 Job 영속화 또는 중복 방지

현재 Job은 단일 FastAPI 프로세스 메모리에 존재한다. 운영 환경에서 여러 Backend 인스턴스를 사용하거나 재시작 내구성이 필요하면 Job 저장소와 중복 저장 정책을 별도로 설계해야 한다.

## 20. 공식 참고 자료

- [Neon: Learn the basics](https://neon.com/docs/get-started/signing-up) — Project, branch, database와 SQL Editor 기본 흐름
- [Neon: AI Concepts](https://neon.com/docs/ai/ai-concepts) — Embedding과 pgvector를 PostgreSQL에 저장하는 개념
- [Neon: Google Colab pgvector guide](https://neon.com/docs/ai/ai-google-colab) — `CREATE EXTENSION vector`, Vector 테이블과 조회 예시
- [Neon: Connect with psql](https://neon.com/docs/connect/query-with-psql-editor) — Dashboard `Connect` 버튼, branch·role·database 선택과 SSL 연결
- [Neon Console Tables 관련 변경 기록](https://neon.com/docs/changelog/2025-03-07) — Console `Tables` 페이지와 SQL Editor 위치 참고

## 21. 최종 요약

이번 작업으로 관리자 OCR 저장 흐름은 다음 실제 구조가 되었다.

```text
OCR
→ 기존 Chunk
→ Gemini 1024차원 Embedding
→ PostgreSQL Transaction
→ Neon admin_documents
→ Neon document_chunks.embedding VECTOR(1024)
```

핵심 확인 기준은 다음 네 가지다.

```text
1. API Response의 documentId가 Neon admin_documents.id에 존재한다.
2. Response의 chunkCount와 Neon document_chunks 행 수가 같다.
3. 모든 Chunk의 document_id가 같은 부모 문서 UUID다.
4. 모든 embedding의 vector_dims() 결과가 1024다.
```

이 네 조건이 충족되면 이번 OCR Chunk Embedding 및 Neon 저장 기능이 정상 작동한 것이다.
