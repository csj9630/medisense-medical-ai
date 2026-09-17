# OCR Chunk 임베딩 및 Neon VectorDB 저장 기능 구현 지시서

## 1. 작업 목표

현재 관리자 OCR 기능은 다음 흐름까지 구현되어 있다.

```text
파일 업로드 → OCR 처리 → 텍스트 추출 → Chunk 분할
```

이번 작업에서는 기존 OCR 구조를 가능한 그대로 유지하면서 아래 흐름만 추가한다.

```text
파일 업로드
→ OCR 처리
→ 텍스트 추출
→ Chunk 분할
→ Chunk Embedding 생성
→ Neon PostgreSQL에 문서 및 Chunk 저장
→ document_chunks.embedding VECTOR(1024) 저장
```

이번 작업의 핵심은 **이미 생성된 OCR Chunk를 그대로 임베딩한 뒤 Neon DB에 저장하는 것**이다.

운영 환경 전체를 설계하거나 RAG 검색 시스템 전체를 구현하는 작업으로 범위를 확장하지 않는다.

---

## 2. 이번 구현 범위

| 기능 | 구현 여부 |
| --- | --- |
| OCR 결과 Chunk 저장 | ✅ |
| Chunk Embedding 생성 | ✅ |
| Neon `VECTOR(1024)` 저장 | ✅ |
| 문서-Chunk 관계 유지 | ✅ |
| 간단한 오류 처리 | ✅ |

---

## 3. 이번 작업에서 제외할 기능

아래 기능은 **이번 작업에서 구현하지 않는다.**

- HNSW / IVFFlat 벡터 인덱스
- Vector 검색 API
- RAG 검색 로직
- Embedding 상태값 관리 (`pending`, `ready`, `error` 등)
- Embedding 모델 버전 이력 관리
- Job 영속화
- Redis / Celery 등 비동기 Queue
- 자동 재시도 시스템
- 관리자 인증 / 권한 시스템
- RLS 정책 변경
- 원본 파일 저장소 재설계
- R2 / S3 비공개 저장소 구성
- Signed URL
- 페이지 / 슬라이드 범위 추적 구조
- OCR 내부 Chunk 구조 대규모 변경
- 프로젝트 전체 DB 스키마 재설계
- 운영환경용 모니터링 시스템

필요 이상으로 구조를 확장하지 않는다.

---

## 4. 기존 프로젝트 구조 유지

기존 프로젝트의 폴더 및 코드 구조를 가능한 유지한다.

특히 이번 기능을 위해 프로젝트 전체 구조를 변경하거나 새로운 대규모 계층을 만들지 않는다.

가능한 한 관리자 OCR 기능 영역 안에서 구현한다.

예상 흐름은 다음과 같다.

```text
admin OCR service
→ 현재 OCR 결과의 Chunk 사용
→ embedding service
→ repository / DB 저장
→ Neon PostgreSQL
```

기존에 Service / Repository 구조가 있다면 이를 그대로 활용한다.

새 파일이 필요한 경우에도 역할을 명확히 나눈다.

예:

```text
services/
    admin_ocr.py
    embedding_service.py

repositories/
    document_repository.py
```

단, 실제 프로젝트 구조를 먼저 확인하고 기존 패턴이 있다면 기존 구조를 우선한다.

---

## 5. 핵심 실행 흐름

이번 기능에는 전체 저장 과정을 관리하는 **하나의 중심 함수**가 존재해야 한다.

예시 이름:

```python
save_ocr_result_with_embeddings(...)
```

함수명은 기존 프로젝트 네이밍 규칙에 맞게 조정해도 된다.

전체 흐름은 다음과 같이 단순하게 유지한다.

```text
OCR 완료
→ OCR에서 이미 생성된 Chunk 목록 확보
→ 문서 정보 준비
→ Chunk들을 Embedding 모델에 전달
→ 각 Chunk의 1024차원 Vector 생성
→ admin_documents에 문서 저장
→ document_chunks에 Chunk + Embedding 저장
→ Transaction commit
→ 저장 성공 결과 반환
```

가능하면 다음과 같이 한 번의 저장 요청 안에서 처리한다.

```text
저장 요청
→ Embedding 생성
→ DB 저장
→ 성공 응답
```

이번 단계에서는 별도의 Background Worker를 만들지 않는다.

---

## 6. OCR Chunk 사용 규칙

현재 OCR 기능에서 이미 Chunk가 생성되고 있으므로 **Chunk 로직을 새로 만들지 않는다.**

현재 생성된 Chunk 결과를 그대로 사용한다.

예:

```python
chunks = [
    "첫 번째 OCR Chunk 내용",
    "두 번째 OCR Chunk 내용",
    "세 번째 OCR Chunk 내용",
]
```

Embedding 단계에서는 각 Chunk의 텍스트를 입력값으로 사용한다.

```text
Chunk Text
→ Embedding Model
→ 1024차원 Vector
```

Chunk 순서는 반드시 유지한다.

각 Chunk는 최소한 다음 관계를 유지해야 한다.

```text
document
 ├─ chunk_index = 0
 ├─ chunk_index = 1
 ├─ chunk_index = 2
 └─ ...
```

---

## 7. Embedding 처리

Embedding 모델은 **1024차원 Vector를 출력하는 모델**을 사용한다.

현재 DB의 컬럼이 다음과 같이 구성되어 있으므로 이를 우선 유지한다.

```text
embedding VECTOR(1024)
```

Embedding 관련 구현은 별도의 함수 또는 Service로 분리한다.

예:

```python
embed_chunks(chunks)
```

입력 예:

```python
[
    "chunk text 1",
    "chunk text 2",
]
```

출력 예:

```python
[
    [0.01, 0.02, ...],  # 1024 dimensions
    [0.03, 0.04, ...],  # 1024 dimensions
]
```

반드시 다음을 검증한다.

- 입력 Chunk 개수와 결과 Vector 개수가 동일한지
- 각 Vector 차원이 정확히 1024인지
- 빈 Chunk가 들어오지 않는지

Embedding 모델 로딩 방식은 기존 프로젝트 환경에 맞게 구현한다.

모델을 요청마다 반복해서 새로 로딩하는 구조는 피한다.

---

## 8. Neon 저장 구조

현재 Neon PostgreSQL의 기존 테이블 구조를 우선 사용한다.

기본 관계는 다음과 같다.

```text
admin_documents
        │
        │ 1 : N
        ▼
document_chunks
```

문서 1개에 여러 Chunk가 연결되어야 한다.

### document 저장

문서 단위 정보는 `admin_documents`에 저장한다.

기존 컬럼을 우선 사용한다.

### Chunk 저장

각 Chunk는 `document_chunks`에 저장한다.

최소 저장 대상:

```text
document_id
chunk_index
chunk_text
embedding
```

실제 컬럼 이름은 현재 모델 및 DB 스키마를 확인하여 기존 이름을 사용한다.

새로운 컬럼을 임의로 추가하지 않는다.

---

## 9. 문서-Chunk 관계 유지

문서를 먼저 저장하여 `document_id`를 확보한 후 해당 ID를 각 Chunk에 연결한다.

예:

```text
admin_documents

id = 15
file_name = sample.pdf
```

```text
document_chunks

document_id = 15
chunk_index = 0
chunk_text = ...
embedding = [...]

document_id = 15
chunk_index = 1
chunk_text = ...
embedding = [...]
```

한 문서의 모든 Chunk가 같은 `document_id`를 가져야 한다.

---

## 10. Transaction 처리

문서와 Chunk 저장은 가능한 한 하나의 Transaction 안에서 처리한다.

예:

```text
Document INSERT
→ Chunk 0 INSERT
→ Chunk 1 INSERT
→ Chunk 2 INSERT
→ Commit
```

중간에 문제가 발생하면 가능한 경우 Rollback 한다.

다음 상태가 발생하지 않도록 한다.

```text
Document는 저장됐는데
Chunk는 일부만 저장된 상태
```

기존 프로젝트에서 SQLAlchemy Session 관리 패턴이 있다면 반드시 기존 방식을 따른다.

---

## 11. 간단한 오류 처리

이번 단계에서는 복잡한 장애 복구 시스템을 만들지 않는다.

최소한 아래 경우만 처리한다.

### OCR Chunk가 없는 경우

```text
저장 중단
→ 적절한 오류 반환
```

### Embedding 생성 실패

```text
DB 저장 중단
→ 오류 로그 기록
→ 실패 응답
```

### Vector 차원이 1024가 아닌 경우

```text
DB 저장 금지
→ 명확한 오류 발생
```

### Neon DB 저장 실패

```text
Rollback
→ 오류 로그 기록
→ 실패 응답
```

### 일부 Chunk만 저장되는 경우

가능한 한 Transaction Rollback으로 전체 저장을 취소한다.

---

## 12. `original_file_url` 처리

현재 `admin_documents.original_file_url`이 필수 컬럼인지 확인한다.

현재 OCR 기능에서 영구적인 원본 파일 URL을 생성하지 않는 경우 이 값 때문에 저장이 실패할 수 있다.

따라서 먼저 현재 코드와 DB 스키마를 확인한다.

처리 원칙:

1. 현재 프로젝트에서 이미 사용할 수 있는 파일 URL이 있으면 그대로 사용
2. 개발 단계에서 사용할 기존 값이 있다면 재사용
3. 이 문제만 해결하기 위해 새로운 R2 / S3 저장 구조를 만들지 않음
4. 컬럼 변경이 필요할 경우 임의 수정하지 말고 어떤 변경이 필요한지 먼저 코드 주석 또는 작업 결과에 명확히 남길 것

이번 작업을 이유로 원본 파일 저장소 구조까지 확장하지 않는다.

---

## 13. API / Frontend 변경 원칙

Frontend 변경은 최소화한다.

현재 OCR 결과 및 Chunk가 Backend에 존재한다면 Frontend가 Chunk 전체를 다시 전송하도록 구조를 크게 변경하지 않는다.

가능하면 기존 저장 버튼 / 저장 API 흐름을 활용한다.

Frontend에서 필요한 것은 최종적으로 다음 정도면 충분하다.

```text
저장 버튼 클릭
→ Backend 저장 요청
→ Embedding + Neon 저장
→ 성공 / 실패 표시
```

UI를 새로 디자인하거나 관리자 페이지 구조를 변경하지 않는다.

---

## 14. 로그

중요 단계에는 기존 프로젝트 로깅 방식을 사용하여 간단한 로그를 남긴다.

예:

```text
[OCR SAVE] document save start
[OCR SAVE] chunks: 12
[EMBEDDING] embedding start
[EMBEDDING] embedding complete
[OCR SAVE] neon insert complete
```

오류 발생 시 어느 단계에서 실패했는지 확인할 수 있어야 한다.

과도한 로그 시스템을 새로 구축하지 않는다.

---

## 15. 코드 작성 규칙

### 기존 구조 우선

새 구조를 만들기 전에 현재 코드의 Service / Repository / Schema / Model 패턴을 확인한다.

### 중심 함수

전체 실행 순서를 파악할 수 있는 중심 함수를 둔다.

### 역할 분리

Embedding 생성과 DB INSERT 로직을 하나의 거대한 함수에 모두 작성하지 않는다.

예:

```text
중심 함수
 ├─ OCR Chunk 가져오기
 ├─ Embedding Service 호출
 └─ Repository 저장 호출
```

### 주석

새로 추가하거나 수정하는 주요 코드에는 한국어 주석으로 기능을 간단히 설명한다.

단순 문법 설명이 아니라 **왜 이 코드가 필요한지** 알 수 있게 작성한다.

---

## 16. 구현 전 반드시 확인할 항목

코드를 수정하기 전에 다음을 먼저 확인한다.

1. 현재 OCR 결과가 어디에 저장되는지
2. Chunk 배열 또는 Chunk 객체가 어떤 형태인지
3. 저장 버튼이 현재 어떤 API를 호출하는지
4. `admin_documents` SQLAlchemy Model
5. `document_chunks` SQLAlchemy Model
6. `embedding VECTOR(1024)` 컬럼이 실제 존재하는지
7. `pgvector` Python 타입 연결이 이미 되어 있는지
8. Neon DB Session / Connection 생성 방식
9. `original_file_url`의 nullable 여부
10. 현재 Service / Repository 구조

확인 후 기존 코드에 가장 적게 손대는 방식으로 구현한다.

---

## 17. 완료 조건

아래 조건을 모두 만족하면 이번 작업은 완료로 본다.

### 1. OCR Chunk 생성

기존 OCR 실행 후 Chunk가 정상적으로 생성된다.

### 2. Embedding 생성

각 Chunk에서 정확히 1024차원의 Vector가 생성된다.

예:

```text
chunk_count = 10
embedding_count = 10
embedding_dimension = 1024
```

### 3. Neon 저장

`admin_documents`에 문서 정보가 저장된다.

`document_chunks`에는 각 Chunk가 저장된다.

각 Chunk에 다음 값이 존재해야 한다.

```text
document_id
chunk_index
chunk_text
embedding
```

### 4. 관계 확인

한 문서의 Chunk들이 동일한 `document_id`로 연결된다.

### 5. DB 직접 확인

Neon에서 직접 조회했을 때 저장된 데이터를 확인할 수 있어야 한다.

예상 확인 대상:

```text
admin_documents
document_chunks
```

### 6. 오류 처리

Embedding 생성 실패 또는 DB 저장 실패 시 API가 무조건 성공으로 응답하지 않아야 한다.

---

## 18. 작업 완료 후 보고

작업 완료 후 다음 형식으로 결과를 정리한다.

### 수정 파일

```text
파일 경로
- 어떤 기능을 수정했는지
```

### 추가된 실행 흐름

```text
OCR
→ Chunk
→ Embedding
→ Neon 저장
```

### Embedding 설정

```text
사용 모델:
Vector Dimension: 1024
```

### Neon 저장 확인

```text
Document 저장 여부:
Chunk 저장 개수:
Embedding 저장 여부:
```

### 테스트 결과

```text
정상 저장 테스트:
Embedding 실패 테스트:
DB 저장 실패 처리:
```

### 남은 사항

이번 범위에서 제외하여 구현하지 않은 내용이 있으면 명시한다.

---

# 최종 구현 원칙

이번 작업에서 가장 중요한 원칙은 다음과 같다.

> **현재 존재하는 OCR Chunk를 그대로 사용하여 1024차원 Embedding을 생성하고 Neon에 저장하는 최소 기능만 구현한다.**

구조를 필요 이상으로 확장하지 않는다.

최종 흐름은 아래 정도로 유지한다.

```text
OCR
→ Chunk
→ Embedding
→ Neon VECTOR(1024)
```

이 기능이 정상적으로 동작하고 Neon에서 저장 결과를 확인할 수 있으면 이번 작업을 완료한다.
