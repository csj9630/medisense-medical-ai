# Backend

## 실행

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item ..\.env.example ..\.env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

- API 문서: http://localhost:8000/docs
- 상태 확인: http://localhost:8000/health
- DB 상태 확인: http://localhost:8000/health/db

프로젝트 최상위 `.env`의 `DATABASE_URL`을 Neon 콘솔에서 복사한 연결 문자열로 교체합니다.
최상위 `.env`가 없는 로컬 환경에서는 기존 `backend/.env`를 fallback으로 읽습니다.

## LLM Provider

Admin LLM, 일반 LLM API, 메인 상담 채팅은 `ai/llm`의 공통 Provider
계약과 Model Registry를 사용합니다.

- `gemma`: Vast.ai의 Gemma 2 2B 한국어 의료 QLoRA
- `medgemma`, `medgemma-dataset`: 하나의 MedGemma 4B base를 공유하는 최종·데이터셋 LoRA
- `qwen`, `llama`: Vast.ai의 Qwen3 4B·Llama 3.2 3B 의료 QLoRA

Admin의 5개 모델은 모두 `remote-http` Provider를 통해 Vast.ai 2× V100 서버를 호출합니다. Gemini LLM은 사용하지 않습니다. OCR과 RAG Embedding은 Vast.ai의 Jina v4·Medical BGE-M3를 호출하며 `EMBEDDING_API_KEY`를 별도로 사용합니다. Backend Key는 Frontend나 로그에 노출하지 않습니다.

Backend의 `app/services/llm_runtime.py`가 환경변수를 공통 Model/Provider Registry로
조립합니다. `app/services/admin_llm.py`는 Admin Schema를, `app/services/llm_service.py`는
`/api/llm/*` Schema를 조립하며, `app/services/message.py`는 메인 대화 저장·RAG·상담
흐름에 공통 Runtime을 연결합니다. Provider 구현과 실행 순서는 `ai/llm`에
존재합니다.

Backend에는 `ai/llm/requirements-api.txt`의 HTTP 의존성만 필요합니다. CUDA와 모델 파일은
Vast.ai 서버에만 있습니다. Admin 모델 가용성 조회는 원격 `/health`만
확인하며, 메인 Catalog 조회는 로컬 Registry만 읽습니다.

메인 페이지는 `GET /api/llm/models`로 모델 Catalog를 읽고,
`POST /api/conversations/{conversation_id}/messages`로 선택한 `model_id`를 전달합니다.
자세한 요청 계약과 실행 흐름은
`docs/3_flow/12_FLW_MainLLM_메인페이지연동가이드_20260831.md`를 참고합니다.

## OCR 문서 처리

두 OCR Endpoint는 `app/services/ocr_workflow.py`를 거쳐 같은 `ai.ocr.analyze_document()`를 호출합니다.

- PDF: Native Text와 포함 이미지를 구분하는 Digital/Scanned/Hybrid 처리
- PNG/JPG: PaddleOCR 처리
- DOCX: `python-docx` 기반 문단·표·이미지 직접 추출
- PPTX: `python-pptx` 기반 슬라이드·도형·표·이미지·발표자 노트 직접 추출
- JSON/JSONL: UTF-8·UTF-16·CP949 디코딩과 JSON 문법 검증 후 직접 추출
- CSV/TXT: UTF-8·UTF-16·CP949 Text 직접 추출
- ZIP: 내부의 지원 문서를 디스크에 풀지 않고 순서대로 통합 추출

DOCX/PPTX 처리를 위해 LibreOffice를 설치하거나 실행 경로를 설정할 필요가 없습니다.
정확한 Office 페이지 미리보기 또는 페이지 번호가 필요하면 원본 프로그램에서 PDF로
내보낸 뒤 PDF를 업로드합니다.

OCR Core는 동기 CPU 작업이며 Backend Adapter가 `asyncio.to_thread()`로 실행해 FastAPI Event Loop를 직접 막지 않습니다. Admin 문자 Chunk, Job 상태와 Vector Save는 Backend에 남아 있습니다.

Admin RAG는 파일당 8GB까지 지원합니다. 20MB 이하는 기존 multipart OCR 경로를,
20MB 초과 JSON·JSONL·CSV·TXT·ZIP은 R2 멀티파트 직접 업로드와 스트리밍 Chunk 경로를
사용합니다. R2 CORS와 Cloud Run CPU 설정은
`docs/r2-admin-rag-uploads.md`를 참고하세요.

## 마이그레이션

```bash
alembic revision --autogenerate -m "create tables"
alembic upgrade head
```

## 기존 Neon 스키마에서 모델 생성

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts/generate_models.py
```

생성 결과는 `app/models/generated.py`에 저장됩니다. 생성된 모델을 검토한 후
`app/models/__init__.py`에서 import하면 Alembic이 해당 모델을 인식합니다.

## ai/ 패키지 (OCR·RAG·LLM)

`ai/ocr`, `ai/rag`는 backend/scripts/Colab이 공통으로 쓰는 독립 패키지다. `requirements.txt`
설치만으로는 `ai` 패키지 자체가 import 가능해지지 않는다 — 저장소 루트를 editable로
한 번 더 설치해야 한다 (repo root의 `pyproject.toml` 참고):

```bash
cd backend
.venv\Scripts\pip install -e ..
.venv\Scripts\pip install -r requirements.txt   # ai/ocr 의존성(paddleocr 등)까지 같이 설치됨
```

`ai/rag`(임베딩/하이브리드 검색, torch 포함이라 더 무거움)까지 쓰려면 추가로:
```bash
.venv\Scripts\pip install -r ../ai/rag/requirements.txt
```

자세한 내용은 `ai/ocr/CLAUDE.md`, `ai/rag/CLAUDE.md`와
`docs/3_flow/11_FLW_LLM_AI코어이관코드비교_20260826.md`를 참고합니다.

⚠️ `ai/ocr`가 `backend/requirements.txt`에 들어가 있어서 documents API의 OCR 기능이
지금은 backend 프로세스 안에서 그대로 돈다 — paddlepaddle만 수백MB라 Docker 이미지가
꽤 커지고, 무료 티어처럼 리소스가 빠듯한 배포 환경에서는 메모리가 부족할 수 있다.
실제 배포 전에 OCR을 별도 워커/서비스로 분리할지 검토할 것.

로컬에서 OCR/임베딩/하이브리드 검색 파이프라인을 직접 테스트해보고 싶으면
`backend/local_lab/`(git 미포함, 개인 로컬 전용)에 라우터+페이지를 만들어서 위 `ai/`
패키지를 호출하는 방식을 쓴다 — `APP_ENV=local`일 때만 `/local-lab`에 자동으로 붙는다.

## 로그인과 이메일 인증

SMTP 및 이메일 인증의 자세한 흐름은 `docs/email-verification.md`를 참고하세요.

비밀번호 재설정 링크 발송과 토큰 처리 흐름은 `docs/password-reset.md`를 참고하세요.

R2 프로필 이미지 저장소 설정은 `docs/r2-profile-images.md`를 참고하세요.
