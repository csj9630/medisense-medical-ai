분석 결과, 현재 Neon 스키마는 기본 골격이 이미 있어서 작업 가능성이 높습니다. 다만 실제 저장 로직은 아직 0%에 가깝고, 스키마·모델만 준비된 상태입니다. 코드·DB·문서는 전혀 수정하지 않았으며 Neon DB에도 접속하지 않았습니다.

## 현재 상태

잘 준비된 부분:

- `admin_documents → document_chunks` 1:N 관계
- 문서 삭제 시 Chunk `ON DELETE CASCADE`
- `embedding VECTOR(1024)` 컬럼
- `document_id` B-tree 인덱스
- SQLAlchemy·psycopg·pgvector 의존성

막혀 있는 부분:

- 저장 버튼은 문서명만 보내며 실제 저장하지 않음
- OCR 본문·Chunk·Chunk Size·Overlap이 저장 API로 전달되지 않음
- Alembic 초기 마이그레이션이 빈 `pass`라 새 DB에 스키마 재현 불가
- `original_file_url`은 필수인데 OCR 원본 파일은 영구 저장하지 않음
- `(document_id, chunk_index)` 중복 방지 제약 없음
- Embedding 모델·버전·생성 상태가 기록되지 않음
- HNSW/IVFFlat 벡터 검색 인덱스 없음
- 명시적인 페이지 범위가 Chunk에 저장되지 않음
- Admin API 인증이 없고 첨부 화면의 RLS도 꺼져 있음

근거는 [generated.py](/C:/Users/2class_18/Documents/CSJ/DEV/thegpt-project/backend/app/models/generated.py:73), [admin_ocr.py](/C:/Users/2class_18/Documents/CSJ/DEV/thegpt-project/backend/app/services/admin_ocr.py:13), [useOcrTest.ts](/C:/Users/2class_18/Documents/CSJ/DEV/thegpt-project/frontend/src/features/admin/hooks/useOcrTest.ts:69), [초기 Alembic migration](/C:/Users/2class_18/Documents/CSJ/DEV/thegpt-project/backend/migrations/versions/5d7e62474617_create_tables.py:15)에서 확인했습니다.

## 권장 진행 순서

```text
OCR Job 완료
→ 관리자가 결과 검토
→ jobId로 서버에 저장 요청
→ 문서 + Chunk를 한 Transaction으로 저장
→ embedding=NULL 상태로 우선 완료
→ 별도 작업에서 로컬 Embedding 생성
→ embedding 상태를 ready로 변경
→ pgvector 검색 연결
```

Frontend가 OCR 본문과 Chunk를 그대로 다시 보내는 방식보다 `jobId`를 전달하고 Backend가 자신이 생성한 결과를 저장하는 방식이 안전합니다. 다만 현재 OCR Job은 메모리에만 있고 60분 후 사라지므로 배포 단계에서는 Job 또는 결과의 영속화도 필요합니다.

스키마에는 최소한 다음 정보가 더 필요합니다.

- 문서: 원본 파일명, MIME, 크기, SHA-256, Chunk Size, Overlap, Chunker 버전
- Embedding: 모델명, 차원, 생성 상태, 오류, 갱신 시각
- Chunk: 페이지/슬라이드 범위 또는 출처 정보
- 제약: `UNIQUE(document_id, chunk_index)`

현재 열어 둔 Qwen3-4B/QLoRA 생성 모델과 Embedding 모델은 별개로 보는 것이 맞습니다. `VECTOR(1024)`를 유지하려면 정확히 1024차원을 출력하는 로컬 Embedding 모델을 따로 선정해야 합니다.

## 개발 공수 견적

1인 개발 기준입니다.

| 범위                |  예상 공수 | 결과                                                   |
| ------------------- | ---------: | ------------------------------------------------------ |
| 텍스트 저장 MVP     |      2~3일 | OCR 본문·Chunk 저장, Transaction, 중복 방지, 테스트    |
| Embedding·검색 기반 | 추가 3~6일 | 로컬 Embedding, 상태 관리, cosine top-k 검색, 인덱스   |
| 배포 안전성 보강    | 추가 3~6일 | 관리자 인증, 비공개 원본 저장, Job 영속화, 장애·재시도 |
| 전체                |  약 8~15일 | 기본적인 RAG 저장·검색 기반과 배포 안전장치            |

페이지 출처를 정확히 보존하도록 OCR 내부 자료구조부터 바꾸면 상단 범위에 가까워집니다.

## Neon 비용 추정

Neon의 현재 Free 요금제는 프로젝트당 월 100 CU-hours와 0.5GB 저장 공간을 제공합니다. Launch는 사용량 기반으로 CU-hour당 `$0.106`, 저장 공간은 GB-month당 `$0.35`이며, 공식적인 간헐적 부하 예시는 월 약 `$15`입니다. [Neon 공식 요금표](https://neon.com/pricing)

현재 512자 Chunk, 약 10% Overlap, 정제 텍스트 2만 자짜리 문서로 가정하면 약 44개 Chunk가 생성됩니다.

- 1024차원 vector 원본: Chunk당 4,104바이트
- 44개 Embedding 원본: 문서당 약 180KB
- 텍스트·전체 OCR 중복 저장·행·인덱스·HNSW 포함 예상: 문서당 약 0.5~0.8MB
- 문서 100개: 약 50~80MB
- 문서 1,000개: 약 0.5~0.8GB

pgvector 공식 계산은 `4 × 차원 + 8바이트`이며, HNSW 인덱스는 검색 성능을 높이는 대신 저장 공간과 메모리를 더 사용합니다. [pgvector 공식 문서](https://github.com/pgvector/pgvector)

따라서:

- 개발·소규모 시험: Neon Free로 충분할 가능성이 높음
- Embedding 없이 텍스트 Chunk만 먼저 저장: Free 한도가 상당히 여유로움
- 1024차원 Embedding과 HNSW를 붙여 수백~천 문서 이상 저장: Launch 전환 가능성 있음
- 로컬 Embedding 생성 비용은 Neon 요금이 아니라 작업 PC의 CPU/GPU 비용

초기에는 HNSW를 바로 만들지 않고 정확 검색으로 시작한 뒤, Chunk가 수만 건 수준으로 늘고 실제 검색 지연을 측정한 후 추가하는 것이 좋습니다. Neon은 pgvector와 HNSW를 지원합니다. [Neon pgvector 안내](https://neon.com/docs/ai/ai-concepts), [검색 최적화 문서](https://neon.com/docs/ai/ai-vector-search-optimization)

## 가장 중요한 주의점

현재 R2 서비스는 공개 URL과 1년 공개 캐시를 사용합니다. 의료 문서 원본 저장에는 그대로 재사용하면 안 됩니다. 원본은 비공개 Object Storage와 제한시간 서명 URL 방식으로 별도 설계해야 합니다.

또한 RLS가 꺼져 있는 것 자체는 FastAPI만 DB에 접근한다면 당장 치명적이지 않지만, Admin API 인증이 없는 현재 상태와 결합하면 배포에는 부적합합니다. 실제 의료·개인정보를 저장한다면 비용보다 인증, 비공개 파일 저장, 접근 기록, 데이터 보존·삭제 정책을 먼저 확정해야 합니다. Neon 요금표상 HIPAA 기능은 Scale 플랜에 표시되어 있으므로 규제 대상 실데이터를 넣을 경우 Free/Launch를 곧바로 운영용으로 간주해서는 안 됩니다.
