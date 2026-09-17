# Embedding Provider 교체 구조 및 1024차원 저장 검증 구현 보고서

- 작업일: 2026-08-23
- 작업 영역: Backend Service Architecture / Configuration / Frontend API Contract / Test
- 대상 기능: OCR Chunk Embedding Provider 교체 경계와 Neon 저장 전 Vector 검증
- 현재 Provider: Google Gemini
- 현재 모델: `gemini-embedding-001`
- 현재 Vector 차원: 1024
- 작업 범위: 공통 Service 계약, 설정 기반 Provider 선택, Provider registry, 저장 직전 차원 재검증, 응답 Provider 정보, 테스트
- 제외 범위: `BAAI/bge-m3` 설치·다운로드·추론, 최종 모델 선정, Neon schema 변경, 기존 Vector 재생성, 검색·RAG 구현

## 1. 작업 목적

현재 `gemini-embedding-001`은 OCR → Chunk → Embedding → Neon 저장 파이프라인이 정상 연결되는지 확인하기 위한 임시 Embedding 모델이다.

팀의 최종 Embedding 모델은 아직 확정되지 않았다. 따라서 이번 작업에서는 `BAAI/bge-m3`로 즉시 교체하거나 BGE용 라이브러리와 모델 파일을 프로젝트에 추가하지 않았다.

대신 다음 원칙을 코드 구조로 고정했다.

```text
중심 OCR 저장 Service
→ 특정 Gemini 클래스에 직접 의존하지 않음
→ 공통 EmbeddingService 계약만 사용
→ 설정값의 Provider 이름으로 구현체 선택
→ 모델명과 Vector 차원도 설정으로 관리
→ Neon 저장 직전에 실제 Vector가 1024차원인지 재검증
```

향후 최종 모델이 정해지면 OCR, Chunk, Repository, Frontend 흐름을 다시 작성하지 않고 새 Provider 구현체와 registry 등록을 중심으로 교체할 수 있게 하는 것이 목적이다.

## 2. 작업 전과 작업 후

### 2.1 작업 전

Embedding 로직 자체는 `embedding_service.py`로 분리되어 있었지만 중심 함수의 타입이 Gemini 구체 클래스에 직접 연결되어 있었다.

```python
embedder: GeminiEmbeddingService
```

설정에는 모델명과 차원은 있었지만 Provider 이름은 별도 설정값이 아니었다.

```text
EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIMENSION=1024
```

즉, 다른 모델로 교체하려면 중심 OCR Service의 타입과 전역 생성 코드를 함께 수정할 가능성이 있었다.

### 2.2 작업 후

```text
EMBEDDING_PROVIDER
EMBEDDING_MODEL
EMBEDDING_DIMENSION
        ↓
create_embedding_service()
        ↓
EMBEDDING_PROVIDER_FACTORIES
        ↓
EmbeddingService 공통 계약 구현체 선택
        ↓
save_ocr_result_with_embeddings()
```

중심 함수는 이제 다음 공통 타입만 사용한다.

```python
embedder: EmbeddingService
```

Gemini를 선택하는 세부 로직은 Provider factory와 registry 안에 있다.

## 3. 변경 후 전체 실행 흐름

기능의 외부 실행 흐름은 변경하지 않았다.

```text
OCR 완료
→ 기존 Chunk 조회
→ 설정된 Embedding Provider 실행
→ Chunk별 Vector 반환
→ 저장 직전 VECTOR(1024) 계약 재검증
→ Neon 문서·Chunk Transaction 저장
→ 기존 성공/실패 UI 표시
```

Frontend의 저장 Endpoint도 그대로다.

```text
POST /api/admin/ocr/vector-save
```

저장 Request도 기존과 같다.

```json
{
  "jobId": "완료된 OCR Job ID"
}
```

## 4. 중심 함수와 호출 관계

중심 함수는 기존과 같은 다음 함수다.

```text
backend/app/services/admin_ocr.py
save_ocr_result_with_embeddings()
```

호출 순서:

```text
save_ocr_result_with_embeddings()

→ OcrJobManager.get_job()
← 완료된 OCR 결과와 기존 Chunk

→ EmbeddingService.embed_chunks()
← 선택된 Provider의 Vector 목록

→ _validate_embeddings_before_storage()
← 저장 가능 또는 명확한 EmbeddingValidationError

→ DocumentRepository.save_with_chunks()
← 저장 documentId와 Chunk 수

→ OcrVectorSaveResponse
```

중심 함수는 Provider가 Gemini인지, 향후 BGE인지 알 필요가 없다. `embed_chunks()`가 공통 계약에 맞는 결과를 반환하는지만 확인한다.

## 5. 공통 Embedding Service 계약

위치:

```text
backend/app/services/embedding_service.py
```

공통 계약:

```python
class EmbeddingService(Protocol):
    provider: str
    model: str
    dimension: int

    async def embed_chunks(
        self,
        chunks: list[str],
    ) -> list[list[float]]: ...
```

각 필드의 의미:

| 필드 | 역할 |
| --- | --- |
| `provider` | 구현 제공자 구분. 현재 `gemini` |
| `model` | 실제 모델 ID. 현재 `gemini-embedding-001` |
| `dimension` | Provider에 요청하고 Neon 저장 전에 검증할 차원. 현재 1024 |
| `embed_chunks()` | Chunk 목록을 같은 순서의 Vector 목록으로 변환 |

`Protocol`을 사용했기 때문에 향후 Provider 클래스가 특정 부모 클래스를 상속할 필요는 없다. 위 속성과 메서드 계약만 만족하면 중심 OCR Service에서 사용할 수 있다.

## 6. 설정값 관리

### 6.1 현재 기본 설정

```dotenv
EMBEDDING_PROVIDER=gemini
EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIMENSION=1024
EMBEDDING_TIMEOUT_SECONDS=60
```

Backend 설정 위치:

```text
backend/app/core/config.py
```

환경변수 예시 위치:

```text
.env.example
```

| 설정 | 현재 값 | 설명 |
| --- | --- | --- |
| `EMBEDDING_PROVIDER` | `gemini` | 어떤 Provider factory를 선택할지 결정 |
| `EMBEDDING_MODEL` | `gemini-embedding-001` | Provider가 사용할 실제 모델명 |
| `EMBEDDING_DIMENSION` | `1024` | Provider 출력 요청 및 저장 계약 검증 |
| `EMBEDDING_TIMEOUT_SECONDS` | `60` | 외부 Provider 응답 제한시간 |

### 6.2 중요한 제한

현재 `EMBEDDING_PROVIDER=bge-m3`로 환경변수만 변경하면 BGE-M3가 실행되는 구조는 아니다.

현재 registry에는 `gemini`만 등록되어 있다.

```python
EMBEDDING_PROVIDER_FACTORIES = {
    "gemini": _create_gemini_embedding_service,
}
```

지원되지 않는 Provider 이름을 설정하면 Backend 시작 시 다음 계열의 명확한 오류가 발생한다.

```text
지원하지 않는 Embedding Provider입니다: bge-m3.
지원 목록: gemini
```

이는 최종 모델 구현이 없는 상태에서 설정 오타나 미완성 Provider가 조용히 실행되는 것을 방지한다.

## 7. 현재 Gemini Provider

현재 실제 구현체는 다음 클래스다.

```text
GeminiEmbeddingService
```

현재 상태:

```text
provider = gemini
model = gemini-embedding-001
dimension = 1024
task_type = RETRIEVAL_DOCUMENT
```

이 모델은 최종 제품 모델로 확정된 것이 아니라 다음 파이프라인 검증에 사용한다.

```text
Chunk 개수 유지
→ 비동기 Provider 호출
→ 1024차원 반환
→ Neon pgvector 저장
→ Transaction 및 오류 응답 확인
```

이번 작업에서는 Gemini 모델을 교체하거나 제거하지 않았고 실제 실행 동작도 유지했다.

## 8. 저장 직전 1024차원 검증

### 8.1 검증 위치

```text
backend/app/services/admin_ocr.py
_validate_embeddings_before_storage()
```

호출 위치는 Embedding 결과를 받은 뒤, Repository를 호출하기 직전이다.

```text
embed_chunks()
→ _validate_embeddings_before_storage()
→ DocumentRepository.save_with_chunks()
```

### 8.2 검증 조건

현재 Neon 컬럼은 다음과 같다.

```sql
embedding VECTOR(1024)
```

저장 전에 다음 조건을 모두 확인한다.

1. 설정된 `EMBEDDING_DIMENSION`이 1024인가
2. OCR Chunk 수와 Embedding 수가 같은가
3. 각 Chunk Vector의 실제 길이가 정확히 1024인가

설정이 768인 경우 예시:

```text
Embedding 설정 차원은 Neon document_chunks.embedding의
VECTOR(1024)와 같아야 합니다. 현재 설정: 768
```

Provider가 설정과 다르게 128차원을 반환한 경우 예시:

```text
Chunk 0의 Embedding 차원은 128입니다.
Neon 저장에는 정확히 1024차원이 필요합니다.
```

### 8.3 실패 시 동작

차원 검증에 실패하면 `EmbeddingValidationError`가 발생한다.

Router는 이를 다음 HTTP 상태로 변환한다.

```text
HTTP 422 Unprocessable Content
```

Repository는 호출되지 않으므로 다음 데이터는 생성되지 않는다.

```text
admin_documents: 저장 안 됨
document_chunks: 저장 안 됨
```

따라서 DB의 `VECTOR(1024)`와 다른 Vector가 부분 저장되는 것을 방지한다.

## 9. Response 변경

성공 Response에 실제 Provider 확인 필드를 추가했다.

```json
{
  "message": "OCR 문서와 Chunk 12개를 VectorDB에 저장했습니다.",
  "documentId": "문서 UUID",
  "chunkCount": 12,
  "embeddingProvider": "gemini",
  "embeddingDimension": 1024,
  "embeddingModel": "gemini-embedding-001"
}
```

이제 로그나 UI 연동 테스트에서 모델명뿐 아니라 어떤 Provider 경로를 사용했는지도 확인할 수 있다.

DB에는 Provider와 모델 버전 이력을 새 컬럼으로 저장하지 않았다. 모델 버전 영속화는 이번 범위에서 제외한 기존 원칙을 유지했다.

## 10. 향후 BGE-M3 교체 방법

### 10.1 이번 작업에서 하지 않은 것

- `sentence-transformers` 또는 FlagEmbedding 설치
- `BAAI/bge-m3` 모델 다운로드
- GPU·CPU 장치 선택 구현
- BGE batch size 및 메모리 정책
- BGE 출력 정규화 정책
- Gemini Vector를 BGE Vector로 재생성
- Provider 간 성능·정확도 비교

### 10.2 최종 모델 확정 후 필요한 구현

예상 순서:

```text
1. BGE Provider 클래스 작성
   ↓
2. EmbeddingService 계약 구현
   provider / model / dimension / embed_chunks 제공
   ↓
3. Provider factory 작성
   ↓
4. EMBEDDING_PROVIDER_FACTORIES에 등록
   ↓
5. EMBEDDING_PROVIDER와 EMBEDDING_MODEL 변경
   ↓
6. 출력 차원이 1024인지 자동 테스트
   ↓
7. 실제 Neon 저장 통합 검증
```

개념 예시이며 현재 코드는 아니다.

```python
class BgeM3EmbeddingService:
    provider = "huggingface"

    def __init__(self, model: str, dimension: int):
        ...

    async def embed_chunks(self, chunks: list[str]) -> list[list[float]]:
        ...
```

factory를 registry에 추가하는 예상 형태:

```python
EMBEDDING_PROVIDER_FACTORIES = {
    "gemini": _create_gemini_embedding_service,
    "huggingface": _create_bge_embedding_service,
}
```

실제 구현 시 Provider 이름은 팀 규칙에 따라 확정해야 한다. 위 이름을 현재 지원한다고 해석하면 안 된다.

### 10.3 차원 변경 시 주의

`BAAI/bge-m3`는 일반적으로 1024차원 Embedding을 사용하는 모델이므로 현재 컬럼과 맞을 가능성이 있지만, 최종 Provider 구현의 실제 반환값을 반드시 런타임에서 검증해야 한다.

향후 768이나 1536차원 모델을 최종 선택하면 환경변수만 바꾸면 안 된다.

```text
Neon schema migration
→ SQLAlchemy model 재생성 또는 갱신
→ 기존 Chunk 전체 재임베딩
→ 검색 Query와 인덱스 재검토
```

서로 다른 모델의 Vector는 의미 공간이 다르므로 같은 컬럼에 혼합 저장한 뒤 검색에 함께 사용하면 안 된다.

## 11. 파일별 변경 내용

| 파일 | 변경 내용 |
| --- | --- |
| `backend/app/core/config.py` | `embedding_provider` 설정 추가 |
| `.env.example` | `EMBEDDING_PROVIDER=gemini` 예시 추가 |
| `backend/app/services/embedding_service.py` | 공통 Protocol, factory, Provider registry 추가 |
| `backend/app/services/admin_ocr.py` | 구체 Gemini 타입 제거, 저장 직전 1024차원 검증 추가 |
| `backend/app/schemas/admin.py` | 성공 Response에 `embeddingProvider` 추가 |
| `frontend/src/features/admin/types/ocr.ts` | Provider Response 타입 반영 |
| `backend/tests/test_ocr_vector_save.py` | Provider 선택과 차원 차단 테스트 추가 |
| `README.md` | Provider 환경설정 예시 추가 |

## 12. 테스트 결과

```text
Backend unittest 전체: 59개 통과
OCR Vector 저장 관련 테스트: 18개 통과
Frontend TypeScript/Vite build: 통과
Pyright: 0 errors, 0 warnings
Python compileall: 통과
git diff --check: 통과
```

이번에 추가 확인한 항목:

- `EMBEDDING_PROVIDER=gemini`이 Gemini 구현체를 선택하는가
- Provider, 모델명, 차원이 설정에서 전달되는가
- 미등록 `bge-m3` Provider가 명확히 거부되는가
- 768차원 설정이 Repository 호출 전에 차단되는가
- Provider가 실제로 128차원을 반환하면 Chunk index와 실제 차원을 포함해 오류를 내는가
- 차원 실패 시 Repository가 호출되지 않는가
- 성공 Response에 `embeddingProvider`가 포함되는가
- 기존 OCR, Chunk, Neon Repository 테스트가 모두 유지되는가

실제 Gemini·Neon 연결은 직전 작업에서 1024차원 Vector 저장·조회·Rollback까지 검증했다. 이번 작업은 Provider 선택 경계와 저장 전 검증을 추가한 구조 변경이며, Gemini API 호출과 Neon Transaction 실행 코드는 변경하지 않았다.

## 13. Mock과 실제 상태 구분

| 항목 | 상태 |
| --- | --- |
| `gemini-embedding-001` | 실제 호출, 파이프라인 테스트용 임시 모델 |
| `GeminiEmbeddingService` | 실제 구현 |
| `EmbeddingService` Protocol | 구현 완료 |
| 설정 기반 Provider 선택 | 구현 완료 |
| Gemini Provider registry | 등록 완료 |
| `BAAI/bge-m3` | 미구현·미등록 |
| 다른 Hugging Face 모델 | 미구현·미등록 |
| 1024차원 저장 직전 검증 | 구현 완료 |
| Neon `VECTOR(1024)` 저장 | 기존 실제 구현 유지 |

## 14. 코드 읽기 순서

```text
1. backend/app/core/config.py
   Provider/모델/차원 설정 확인
   ↓
2. backend/app/services/embedding_service.py
   공통 Protocol과 Provider registry 확인
   ↓
3. backend/app/services/admin_ocr.py
   중심 함수와 저장 전 검증 확인
   ↓
4. backend/app/api/admin/router.py
   422 오류 변환 확인
   ↓
5. backend/app/schemas/admin.py
   Provider 포함 Response 확인
   ↓
6. backend/tests/test_ocr_vector_save.py
   교체 경계와 차원 오류 테스트 확인
```

## 15. 작업 시 주의사항

- 팀 결정 전 `EMBEDDING_PROVIDER`를 임의로 BGE 계열 값으로 바꾸지 않는다.
- `EMBEDDING_MODEL`만 BGE 이름으로 바꾸고 Provider를 Gemini로 두면 Gemini API에 잘못된 모델명을 요청하게 된다.
- 새 Provider는 반드시 `EmbeddingService` 계약을 구현하고 registry에 등록한다.
- 새 Provider의 설정 차원뿐 아니라 실제 반환 Vector 길이를 테스트한다.
- Neon 컬럼이 `VECTOR(1024)`인 동안 1024 이외 Vector는 저장하지 않는다.
- 최종 모델 변경 시 기존 Gemini Vector와 새 모델 Vector를 혼합하지 않는다.
- 로컬 모델은 요청마다 다시 로딩하지 말고 프로세스에서 재사용하도록 설계한다.
- GPU 사용 여부, batch size, 정규화, 최대 token 길이는 최종 모델 선정 후 별도로 결정한다.
- OCR Chunk 원문을 외부 Gemini에 전송하는 현재 개인정보 정책도 최종 Provider 결정 시 다시 검토한다.

## 16. 최종 상태

```text
현재

OCR
→ Chunk
→ EmbeddingService 공통 계약
→ EMBEDDING_PROVIDER=gemini
→ GeminiEmbeddingService
→ gemini-embedding-001, 1024차원
→ 저장 직전 VECTOR(1024) 검증
→ Neon 저장
```

```text
향후 최종 모델 확정 후

OCR
→ Chunk
→ 같은 EmbeddingService 공통 계약
→ 새 Provider 구현체
→ 저장 직전 VECTOR(1024) 검증
→ 같은 Neon Repository
```

이번 작업은 BGE-M3 전환 작업이 아니다. 현재 Gemini 모델을 파이프라인 테스트용으로 유지하면서, 팀 결정 후 모델 교체가 OCR과 저장 흐름 전체의 재작성으로 이어지지 않도록 Provider 경계를 만든 작업이다.
