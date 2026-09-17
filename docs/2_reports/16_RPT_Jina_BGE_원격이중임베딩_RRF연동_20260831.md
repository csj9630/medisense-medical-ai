# Jina v4·Medical BGE-M3 원격 이중 Embedding과 RRF 연동

- 작업일: 2026-08-31
- 작업 영역: Backend / AI RAG / pgvector
- 실행 환경: Vast.ai GPU Embedding API + FastAPI CPU Backend + Neon PostgreSQL
- 작업 범위: OCR 이중 Vector 저장, 질문 이중 검색, RRF, 메인 상담 LLM Context 연결
- 제외 범위: Vast.ai Instance 자동 배포, 기존 Gemini Vector 자동 Backfill

## 1. 목적

기존 `dev`에는 Provider 수에 제한이 없는 `chunk_embeddings` 테이블과
RRF·메인 채팅 RAG 연결이 이미 구현되어 있었지만, 실제 Provider는 hashing
Placeholder였다. 이번 작업에서 Vast.ai의 Jina v4와 의료 파인튜닝
BGE-M3를 공통 Provider 계약에 연결했다.

## 2. 최종 실행 흐름

```text
Admin OCR 저장
→ Jina passage Vector + Medical BGE passage Vector
→ admin_documents + document_chunks + chunk_embeddings 하나의 Transaction

메인 사용자 질문
→ Jina query Vector + Medical BGE query Vector
→ provider_name별 pgvector Top 20
→ Chunk UUID 기반 RRF(k=60)
→ 최종 Top K Chunk
→ ai.consultation Prompt Context
→ 선택한 Vast.ai LLM 답변
```

`document_chunks.embedding`의 기존 Gemini Vector는 삭제하지 않았다. 새 OCR
저장은 `chunk_embeddings` 테이블에 Provider별 행을 생성하며, 새 RAG도 이
테이블만 사용한다.

## 3. 원격 API 계약

```http
POST {EMBEDDING_REMOTE_BASE_URL}/v1/embeddings
Authorization: Bearer <EMBEDDING_API_KEY>
Content-Type: application/json
```

```json
{
  "model": "jina-v4",
  "input_type": "passage",
  "texts": ["청크 1", "청크 2"]
}
```

```json
{
  "model": "jina-v4",
  "dimensions": 1024,
  "embeddings": [[0.01, 0.02], [0.03, 0.04]]
}
```

실제 Vector는 각각 1024개 숫자를 포함해야 한다. Backend는 응답의
모델명, 개수, 차원, NaN/Infinity, 0 Vector를 검증하고 단위 Vector로
정규화한다.

Jina v4는 기본 dense 출력이 2048차원이므로 Notebook에서
`task="retrieval"`, `truncate_dim=1024`, `prompt_name="query"` 또는
`"passage"`를 반드시 적용해야 한다.

## 4. 환경변수

```dotenv
EMBEDDING_REMOTE_BASE_URL=https://embedding.example.com
EMBEDDING_API_KEY=실제_Embedding_API_Key
EMBEDDING_JINA_MODEL=jina-v4
EMBEDDING_BGE_MODEL=medical-bgem3
EMBEDDING_DIMENSION=1024
EMBEDDING_TIMEOUT_SECONDS=60
EMBEDDING_BATCH_SIZE=32
RAG_EMBEDDING_PROVIDER=remote_dual
```

Base URL에 `/v1/embeddings`를 직접 붙이지 않는다. Key는 Backend전용이며
`VITE_` 접두사를 붙이거나 Git에 커밋하지 않는다.

## 5. 변경 파일

| 파일 | 역할 |
|---|---|
| `ai/rag/embeddings/remote.py` | Bearer HTTP query/passage Provider와 응답 검증 |
| `backend/app/core/rag_embedding.py` | Jina/BGE 두 Provider를 OCR·RAG 공통 설정으로 조립 |
| `backend/app/services/embedding_service.py` | OCR에서 두 Provider를 동시 호출 |
| `backend/app/services/admin_ocr.py` | 이중 Vector 검증과 Transaction 저장 조율 |
| `backend/app/repositories/document_repository.py` | Provider별 `chunk_embeddings` 행 저장 |
| `ai/rag/hybrid.py` | Integer와 UUID를 모두 지원하는 범용 RRF |

기존 `rag_search_service.py` 및 `message.py`가 Provider 추상화를 사용하고 있어
이 두 파일을 변경하지 않고도 메인 채팅까지 실제 모델이 연결된다.

## 6. 검증

- 원격 query/passage HTTP 계약, Bearer 인증, Batch, 정규화
- 잘못된 차원·설정·HTTP 오류 처리
- OCR Chunk 2개 × Provider 2개의 동일 Transaction 저장
- Jina/BGE Top 20 순위의 UUID RRF 합성
- Backend 및 공통 AI 회귀 테스트

실제 Vast.ai URL과 Key는 저장소에 넣지 않았다. 배포 환경의 `.env`를
설정한 후 민감하지 않은 문장으로 Admin OCR 저장과 메인 채팅 Smoke Test를
최종 1회 실행해야 한다.
