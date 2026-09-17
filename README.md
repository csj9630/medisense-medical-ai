# MediSense

> **RAG · OCR · LLM Fine-tuning을 활용한 의료 상담 보조 웹 서비스**

MediSense는 사용자의 의료 관련 질문에 대해 **응급 가능성을 우선 확인하고**, 의료 문서 검색 결과와 진료과 힌트를 기반으로 LLM이 참고용 답변을 생성하는 팀 프로젝트입니다.  
React/FastAPI 기반 웹 서비스에 PostgreSQL·pgvector, OCR, RAG, 원격 의료 LLM을 통합했습니다.

> **주의:** 본 프로젝트는 교육 과정에서 개발한 의료 상담 **프로토타입**이며, 의료진의 진단이나 치료를 대체하지 않습니다.

---

## 1. 프로젝트 개요

| 항목 | 내용 |
|---|---|
| 프로젝트명 | MediSense |
| 개발 기간 | 2026.08 ~ 2026.09 |
| 형태 | 팀 프로젝트 |
| 주요 주제 | 의료 상담 AI, RAG, OCR, LLM Fine-tuning |
| Frontend | React, TypeScript, Vite |
| Backend | FastAPI, SQLAlchemy |
| Database | PostgreSQL / Neon, pgvector |
| AI | LLM, QLoRA/LoRA, RAG, PaddleOCR |

### 목표

단순한 LLM 질의응답을 넘어 다음 기능을 하나의 서비스 흐름으로 연결하는 것을 목표로 했습니다.

- 의료 상담 대화 및 대화 이력 관리
- 응급 표현 감지 및 고정 안전 안내
- 규칙 기반 진료과 분류
- 의료 문서 기반 RAG 검색
- 다중 LLM 비교 및 평가
- 문서 OCR → 정제 → 청킹 → 임베딩 → Vector DB 저장
- 관리자용 OCR/RAG 및 LLM 비교 기능

---

## 2. 주요 기능

### 의료 상담

사용자 질문을 저장하고 최근 대화 문맥, 진료과 분류 결과, RAG 검색 결과를 결합해 선택된 원격 LLM에 전달합니다.

```text
사용자 질문
   ↓
응급 표현 감지
   ↓
진료과 분류
   ↓
RAG 검색
   ↓
최근 대화 + 검색 근거 + 현재 질문
   ↓
LLM 생성
   ↓
응답 후처리
   ↓
대화 / 상담 로그 저장
```

- 최근 완결된 대화 최대 **6턴 / 6,000자**를 상담 문맥으로 사용
- 응급 표현 감지 시 LLM 호출을 생략하고 고정 안내 반환
- RAG 장애 시 근거 없이 LLM 상담을 계속하는 fallback 적용
- LLM 장애 시 고정 안전 안내 반환

### RAG

운영 검색은 두 dense embedding 결과를 결합하는 구조입니다.

```text
Query
 ├─ Jina v4 Embedding
 └─ Medical BGE-M3 Embedding
        ↓
  pgvector 검색
        ↓
 Reciprocal Rank Fusion
        ↓
 source / 진료과 metadata 보정
        ↓
   최종 Context
```

- Jina v4 + Medical BGE-M3
- Embedding dimension: 1024
- PostgreSQL / pgvector
- Reciprocal Rank Fusion(RRF)
- 문서 신뢰도 및 진료과 metadata 기반 soft boost
- 선택적으로 BGE reranker 사용 가능

> 현재 운영 검색은 **Dense + Dense RRF** 구조이며, BM25 코드는 비교 실험용으로 존재합니다.

### OCR / 문서 처리

관리자 기능을 통해 의료 문서를 OCR/RAG 데이터로 가공할 수 있습니다.

지원 형식:

`PDF`, `PNG`, `JPG`, `DOCX`, `PPTX`, `JSON`, `JSONL`, `CSV`, `TXT`, `ZIP`

주요 처리 흐름:

```text
파일 / URL
   ↓
텍스트 추출 또는 OCR
   ↓
정제
   ↓
Chunk 생성
   ↓
Embedding
   ↓
PostgreSQL / pgvector 저장
```

### LLM 비교

관리자 페이지에서 여러 의료 LLM을 동일 입력으로 비교할 수 있도록 구성했습니다.

코드상 등록 모델:

- Gemma
- MedGemma Final
- MedGemma Dataset
- Qwen
- Llama

모델별 응답, 실행 시간, token 사용량 등을 비교하도록 구현되어 있습니다.

---

## 3. 담당 업무

> 아래 내용은 **프로젝트 전체 기능이 아니라 개인 담당 및 직접 수행한 작업**을 기준으로 정리했습니다.

### 3.1 Qwen3-4B Fine-tuning 및 평가

**Qwen3-4B 의료 상담 모델의 QLoRA Fine-tuning과 평가를 담당했습니다.**

- Qwen3 소형 모델을 이용한 QLoRA 학습 환경 검증
- Qwen3-4B 대상 의료 상담 Fine-tuning 진행
- 의료 대화 데이터셋 병합 및 Train / Eval 데이터 구성
- LoRA `r=16`, `alpha=32`, `dropout=0.05` 기반 실험
- 학습 로그 및 validation 결과 확인
- Fine-tuning 전후 답변 특성 비교
- 객관식 / 상담형 / 모호 질문 / 응급 질문으로 평가 유형을 분리하여 결과 분석

Fine-tuning 결과에서는 의료 지식 및 환각 억제 측면의 개선과 함께, 답변이 지나치게 짧아지거나 단정적으로 변하는 현상도 확인해 후속 프롬프트 실험에 반영했습니다.

### 3.2 의료 상담 Prompt Engineering

**의료 상담용 프롬프트를 반복 설계하고 동일 평가셋으로 버전별 응답을 비교했습니다.**

- 의료 상담 Prompt v1 ~ v4 계열 설계 및 실험
- 상담형·모호형·응급형 질문을 중심으로 응답 비교
- 진단 단정 억제
- 불필요한 약물 용량·복용 지시 제한
- 추가 확인 질문 유도
- RAG Context 사용 규칙 설계
- 응급 상황 우선 안내 규칙 실험
- 반복 응답 및 형식 문제 분석
- generation option과 prompt 역할을 분리하여 문제 원인 분석

실험 과정에서 **규칙을 계속 추가하는 것만으로는 모든 문제를 해결할 수 없으며**, 응급 판별처럼 결정적인 안전 로직은 Prompt 외부의 별도 처리로 분리할 필요가 있다는 결론을 얻었습니다.

이에 최종 상담 흐름에서는 응급 표현을 사전에 검사하고, 감지 시 LLM을 호출하지 않는 구조를 적용했습니다.

### 3.3 LLM 비교 및 실행 구조

Fine-tuning 모델을 서비스에서 비교하기 위한 실행·평가 구조 작업에 참여했습니다.

- Fine-tuning 모델 비교 대상 및 평가 기준 정리
- 동일 질문을 여러 모델에서 실행하는 비교 방식 설계
- 모델별 응답 시간 / token 사용량 비교 요구사항 정의
- Qwen 계열 모델 실행 및 API 연동 환경 구성
- Llama 소량 Fine-tuning 및 비교 실험
- 로컬/원격 LLM 실행 구조 검토
- 관리자 LLM 비교 화면 요구사항 및 동작 구조 정리

모델의 단순 정답률만 비교하지 않고 **상담 문맥, 응급 대응, 답변 안정성, 환각 여부**를 함께 평가 대상으로 사용했습니다.

### 3.4 Admin OCR / RAG 및 데이터 처리

관리자 페이지의 **문서 입력 → OCR/텍스트 처리 → RAG 저장 흐름** 관련 작업을 담당했습니다.

- Admin OCR/RAG 기능 구조 분석 및 개발
- 파일 및 웹 URL 기반 문서 처리 흐름 정리
- OCR 결과 미리보기 및 텍스트 처리
- 불필요한 중복 제거와 원문 구조를 가능한 한 유지하는 정제 방식 검토
- RAG용 Chunk 및 metadata 구조 검토
- Embedding Model 교체가 가능한 구조 작업
- PostgreSQL/Neon + pgvector 저장 구조 확인
- 파일 업로드 → 정제 → 임베딩 → Vector DB 저장 흐름 점검
- Vector dimension 등 RAG 저장 구조의 불일치 문제 확인

특히 OCR 결과를 단순 요약문으로 바꾸기보다 **검색 근거로 사용할 수 있는 원문 정보를 최대한 보존하는 방향**을 우선했습니다.

### 3.5 테스트 및 프로젝트 문서화

프로젝트 마무리 단계에서 구현 내용과 시행착오를 재검토하고 문서화했습니다.

- 화면정의서 작성 및 실제 구현 화면 정리
- 프로젝트 단위 테스트 항목 검토
- LLM / Prompt 실험 결과 보고서 작성
- RAG 검색 실패 사례 및 개선 방향 정리
- 발표 자료의 LLM 모델 비교 / Prompt Engineering 파트 구성
- 프로젝트 전체 구조 및 최종 코드 상태 재분석

---

## 4. 시스템 구조

```text
Browser
  │
  ▼
React / TypeScript
  │
  ▼
FastAPI
  ├─ Auth
  ├─ Conversation
  ├─ Admin
  ├─ Evaluation
  │
  ├─ Service Layer
  │   ├─ Consultation
  │   ├─ OCR
  │   ├─ RAG
  │   └─ LLM Runtime
  │
  ├─ AI Core
  │   ├─ Prompt / Emergency Detection
  │   ├─ OCR
  │   ├─ Embedding / Retrieval
  │   └─ LLM Provider
  │
  └─ Repository
       │
       ▼
PostgreSQL / pgvector
```

외부 서비스:

- Remote LLM Server
- Remote Jina / BGE Embedding Server
- Cloudflare R2
- Google / GitHub OAuth
- SMTP
- Hugging Face
- KDCA OpenAPI

---

## 5. 프로젝트 구조

```text
thegpt-project/
├─ ai/
│  ├─ consultation/       # 상담 흐름, Prompt, 응급 감지
│  ├─ evaluation/         # 답변 및 Retrieval 평가
│  ├─ llm/                # LLM Provider / Registry
│  ├─ ocr/                # OCR Core
│  └─ rag/                # Chunking, Embedding, Retrieval
│
├─ backend/
│  ├─ app/
│  │  ├─ api/             # FastAPI Router
│  │  ├─ services/        # Business Logic
│  │  ├─ repositories/    # DB Access
│  │  ├─ schemas/
│  │  ├─ models/
│  │  └─ core/
│  ├─ migrations/
│  └─ tests/
│
├─ frontend/
│  ├─ src/
│  │  ├─ api/
│  │  ├─ app/
│  │  ├─ components/
│  │  ├─ features/
│  │  ├─ services/
│  │  └─ utils/
│  └─ tests/
│
├─ scripts/
│  ├─ RAG ingestion / retrieval benchmark
│  ├─ Fine-tuning notebooks
│  └─ Remote LLM server
│
├─ tests/
└─ docs/
```

---

## 6. 기술 스택

### Frontend

- React 19
- TypeScript
- Vite
- React Router
- Tailwind CSS
- Context API
- Fetch API

### Backend

- Python
- FastAPI
- SQLAlchemy
- Pydantic
- Alembic
- PostgreSQL
- pgvector
- PyJWT

### AI / LLM

- Hugging Face Transformers
- PEFT
- QLoRA / LoRA
- bitsandbytes
- Accelerate
- TRL
- Gemma
- MedGemma
- Qwen3
- Llama

### RAG / OCR

- Jina Embedding v4
- Medical BGE-M3
- PaddleOCR
- PaddlePaddle
- OpenCV
- PyMuPDF
- python-docx
- python-pptx

### Infra

- Neon / PostgreSQL
- Cloudflare R2
- Cloudflare
- Google Cloud Build
- Google Cloud Run
- Hugging Face

---

## 7. 실행 환경

### Backend

Windows 개발 환경에서는 Python 3.12 기반 가상환경을 사용합니다.

```bash
py -3.12 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
backend\.venv\Scripts\python.exe -m pip install -e .
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

### Frontend

Vite 8 기준 Node.js `^20.19.0` 또는 `>=22.12.0` 환경이 필요합니다.

```bash
cd frontend
npm install
npm run dev
```

### 통합 실행

Windows 환경:

```bash
.\run.bat
```

기본 개발 주소:

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- Health Check: `http://localhost:8000/health`

---

## 8. 환경 변수

프로젝트 루트의 `.env.example`을 참고해 `.env`를 구성합니다.

주요 설정 영역:

- PostgreSQL / Neon
- JWT
- Google / GitHub OAuth
- SMTP
- Cloudflare R2
- Remote LLM
- Remote Embedding
- OCR
- RAG

```bash
Copy-Item .env.example .env
```

> API Key, Password, Token 등 실제 Secret 값은 저장소에 Commit하지 않습니다.

---

## 9. 현재 확인된 제한사항

프로젝트 종료 시점의 정적 코드 분석을 기준으로 다음 제한사항이 확인되었습니다.

### Database Migration

초기 Alembic baseline이 비어 있어 **새로운 빈 DB에서 `alembic upgrade head`만으로 전체 DB를 재현할 수 없는 상태**입니다.

### Vector Dimension

`chunk_embeddings.embedding`의 ORM 정의와 최신 Migration/Repository 간에 `2048 ↔ 1024` 차원 불일치가 남아 있습니다.

### 채팅 파일 첨부

채팅의 첨부파일은 확장자 및 크기 검증과 미리보기에 사용되지만, 현재 상담 LLM 입력에는 파일 본문이 직접 포함되지 않습니다.

### RAG 검색

운영 검색은 **Jina + BGE dense retrieval의 RRF 결합**입니다. BM25/Kiwi 검색은 비교 실험 코드에는 존재하지만 현재 상담 검색 경로에는 연결되지 않습니다.

### 의료 안전

응급 표현 감지는 규칙 기반 정규식을 사용합니다. 실제 의료 서비스에 적용하려면 의료 전문가에 의한 검증과 별도의 acceptance test가 필요합니다.

---

## 10. 프로젝트를 통해 배운 점

### Fine-tuning만으로 원하는 답변이 만들어지지는 않는다

Fine-tuning을 적용하면 의료 지식이나 특정 응답 경향을 강화할 수 있었지만, 상담 품질 전체를 Fine-tuning 하나만으로 해결할 수는 없었습니다.

### Prompt 규칙을 늘리는 것에도 한계가 있다

응급 대응을 강화하기 위해 규칙을 늘릴수록 불필요한 과대 대응이나 답변 지연 같은 다른 문제가 발생했습니다.

결국 응급 판단처럼 중요한 규칙은 Prompt에만 의존하지 않고 **LLM 외부의 결정적 로직으로 분리**하는 방향이 더 안정적이었습니다.

### RAG는 데이터를 넣는 것보다 검색 품질 검증이 중요하다

Vector DB에 문서를 많이 저장한다고 검색 품질이 자동으로 좋아지지 않았습니다.

Embedding Model, Chunk 구조, Metadata, Filtering, Reranking 등 검색 파이프라인 전체를 함께 확인해야 했고, 실제 실패 질문을 기준으로 Retrieval 결과를 점검하는 과정이 중요했습니다.

### AI 기능도 결국 하나의 Backend 기능이다

프로젝트 초기에는 Fine-tuning, Prompt, RAG, OCR을 각각 별개의 AI 기술로 생각했지만, 실제 서비스를 구성하면서 이 기능들이 API, DB, 인증, 오류 처리, 저장 정책과 함께 연결되어야 한다는 점을 경험했습니다.

---

## 11. Project Status

MediSense는 교육 과정의 메인 프로젝트로 개발된 **의료 AI 통합 프로토타입**입니다.

인증, 대화 저장, 의료 상담, LLM, RAG, OCR, Vector DB, 관리자 기능까지 주요 서비스 흐름은 코드로 연결되어 있지만, 실제 운영 서비스 수준의 의료 검증·보안·DB 재현성·인프라 안정성까지 완료된 프로젝트는 아닙니다.

프로젝트 종료 시점의 구현 상태와 한계를 함께 기록하는 것을 원칙으로 합니다.
