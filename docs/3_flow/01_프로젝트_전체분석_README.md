# 프로젝트 구조 분석

> 분석 기준: 2026-08-17 현재 저장소의 실제 코드와 설정 파일. 자동 생성 산출물, 의존성 디렉터리, 캐시, Git 내부 파일은 제외했다. 환경변수는 이름만 기록하며 실제 값은 포함하지 않는다.

## 1. 프로젝트 개요

이 저장소는 의료 AI 상담 화면을 목표로 하는 모노레포 형태의 프로젝트다.

- `frontend`: React 19 + TypeScript + Vite 기반 SPA
- `backend`: FastAPI + SQLAlchemy 기반 REST API
- `ai`: 상담, 평가, LLM, OCR, RAG 기능을 위한 자리만 마련된 디렉터리
- 현재 실제 end-to-end 연결은 회원가입, 이메일 인증, 로그인, 비밀번호 관리, 마이페이지, 프로필 이미지 업로드 중심이다.
- 상담/채팅 UI는 동작하지만 브라우저 메모리 mock 데이터를 사용하며 FastAPI나 LLM에는 연결되지 않는다.
- 문서, OCR, 검색, 평가, 관리자 기능은 화면 또는 빈 라우터 수준이다.

## 2. 기술 스택

### Frontend

| 기술 | 확인 버전/범위 | 용도 |
|---|---:|---|
| React / React DOM | `^19.2.8` | UI |
| TypeScript | `^5.9.3` | 정적 타입 |
| Vite | `^8.2.1` | 개발 서버와 빌드 |
| React Router DOM | `^7.18.2` | 브라우저 라우팅 |
| Tailwind CSS | `^4.3.3` | 유틸리티 기반 스타일 |
| lucide-react | `^1.31.0` | 아이콘 |
| Playwright | `^1.62.1` | 브라우저 테스트 의존성(테스트 파일/스크립트는 없음) |

### Backend

| 기술 | 확인 버전 범위 | 용도 |
|---|---:|---|
| FastAPI | `>=0.116,<1.0` | REST API |
| Uvicorn | `>=0.35,<1.0` | ASGI 서버 |
| SQLAlchemy | `>=2.0,<3.0` | ORM과 DB 세션 |
| Pydantic Settings | `>=2.10,<3.0` | 환경설정 |
| Psycopg | `>=3.2,<4.0` | PostgreSQL 드라이버 |
| Alembic | `>=1.16,<2.0` | DB 마이그레이션 |
| pgvector | `>=0.4,<1.0` | PostgreSQL 벡터 컬럼 |
| PyJWT | `>=2.10,<3.0` | 인증/비밀번호 재설정 토큰 |
| pwdlib[argon2] | `>=0.3,<1.0` | 비밀번호 해시 |
| boto3 | `>=1.40,<2.0` | Cloudflare R2의 S3 호환 API |

### 인프라 및 데이터

- PostgreSQL/Neon을 전제로 한 `app_db`, `vector_db` 스키마와 pgvector 모델이 존재한다.
- 로컬 기본 `DATABASE_URL`은 SQLite지만, 생성 모델과 마이그레이션에는 PostgreSQL 전용 스키마, `gen_random_uuid()`, `VECTOR(1024)`가 포함된다.
- Cloudflare R2에 프로필 이미지를 저장하는 서비스가 구현되어 있다.
- `cloudbuild.yaml`, 백엔드 Dockerfile, 프론트엔드 `wrangler.jsonc`가 존재한다.

## 3. 전체 디렉터리 구조

```text
thegpt-project/
├─ ai/
│  ├─ consultation/              # .gitkeep만 존재
│  ├─ evaluation/                # .gitkeep만 존재
│  ├─ llm/                       # .gitkeep만 존재
│  ├─ ocr/                       # .gitkeep만 존재
│  └─ rag/                       # .gitkeep만 존재
├─ backend/
│  ├─ app/
│  │  ├─ api/
│  │  │  ├─ admin/router.py
│  │  │  ├─ auth/                # 인증·가입·비밀번호·프로필·마이페이지 라우터
│  │  │  ├─ consultation/router.py
│  │  │  ├─ documents/router.py
│  │  │  ├─ evaluations/router.py
│  │  │  └─ router.py            # 하위 라우터 통합
│  │  ├─ core/                    # 앱, DB, SMTP, R2 설정
│  │  ├─ models/generated.py      # DB에서 생성한 SQLAlchemy 모델
│  │  ├─ repositories/            # DB 접근 계층
│  │  ├─ schemas/                 # Pydantic 요청/응답 모델
│  │  ├─ services/                # 인증·메일·프로필·계정 비즈니스 로직
│  │  ├─ utils/                   # 현재 __init__.py만 존재
│  │  └─ main.py                  # FastAPI 진입점
│  ├─ docs/                       # 이메일 인증, 비밀번호 재설정, R2 문서
│  ├─ migrations/versions/5d7e62474617_create_tables.py
│  ├─ scripts/generate_models.py
│  ├─ .env.example
│  ├─ alembic.ini
│  ├─ dockerfile
│  ├─ requirements.txt
│  └─ requirements-dev.txt
├─ frontend/
│  ├─ src/
│  │  ├─ api/                     # 상담/메시지 mock 데이터 계층
│  │  ├─ app/                     # App, Router, 전역 CSS
│  │  ├─ components/
│  │  │  ├─ Chat/
│  │  │  ├─ CursorFx/
│  │  │  ├─ Layout/
│  │  │  ├─ Sidebar/
│  │  │  └─ Theme/
│  │  ├─ features/
│  │  │  ├─ admin/
│  │  │  ├─ auth/
│  │  │  ├─ chat/
│  │  │  ├─ consultation/
│  │  │  ├─ document/
│  │  │  ├─ evaluation/
│  │  │  ├─ my/
│  │  │  ├─ ocr/
│  │  │  └─ search/
│  │  ├─ services/apiClient.ts
│  │  ├─ global.d.ts
│  │  └─ main.tsx
│  ├─ .env.example
│  ├─ index.html
│  ├─ package.json
│  ├─ tsconfig.json
│  ├─ vite.config.ts
│  └─ wrangler.jsonc
├─ cloudbuild.yaml
└─ README.md
```

## 4. Frontend 구조

`main.tsx`가 전역 CSS를 불러오고 `<App />`을 마운트한다. `App`은 전역 Context Provider와 Router를 조합한다. 별도 `layouts/` 디렉터리 대신 `components/Layout/MainLayout.tsx`가 공통 레이아웃을 담당한다.

```text
StrictMode → App → ThemeProvider → AuthProvider → ModelSelectProvider
→ CursorFxProvider → RouterProvider → MainLayout
→ SidebarProvider → DocumentPreviewProvider
→ Sidebar + Outlet(각 Page) + 선택적 DocumentPreviewPanel
```

### 4.1 Routing

| URL | 페이지 | 접근 | 현재 역할 |
|---|---|---|---|
| `/` | `ConsultationPage` | 공개 | 새 mock 대화를 만들고 채팅으로 이동 |
| `/chat/:conversationId` | `ChatPage` | 공개 | mock 메시지 조회/전송과 첨부파일 UI |
| `/login` | `LoginPage` | 공개 | 백엔드 로그인 API 호출 |
| `/signup` | `SignupPage` | 공개 | 회원가입 후 이메일 인증 흐름 |
| `/verify-email` | `VerifyEmailPage` | 공개 | 인증 코드 확인/재발송 |
| `/forgot-password` | `ForgotPasswordPage` | 공개 | 비밀번호 재설정 링크 요청 |
| `/reset-password` | `ResetPasswordPage` | 공개 | 토큰 검증과 새 비밀번호 설정 |
| `/document` | `DocumentPage` | 공개 | 제목만 표시하는 placeholder |
| `/ocr` | `OcrPage` | 공개 | 제목만 표시하는 placeholder |
| `/search` | `SearchPage` | 공개 | 제목만 표시하는 placeholder |
| `/evaluation` | `EvaluationPage` | 공개 | 제목만 표시하는 placeholder |
| `/admin` | `AdminPage` | 공개 | 제목만 표시하며 관리자 권한 보호 없음 |
| `/mypage`, `/my` | `MyPage` | 로그인 필요 | 계정·사용량·모델 선택·삭제 기능 |

명시적 404 라우트는 없다. `RequireAuth`는 인증되지 않은 사용자를 `/login`으로 보낸다.

### 4.2 Layout

- 모든 라우트가 `MainLayout` 아래에 있어 로그인/가입 화면에도 Sidebar와 ThemeToggle이 함께 표시된다.
- 레이아웃은 전체 화면 flex 구조이며 `Sidebar`, 중앙 `Outlet`, 선택적 우측 문서 미리보기 패널로 구성된다.
- Sidebar 축소, 문서 미리보기, 테마, AI 모델, 커서 효과는 각각 React Context로 관리된다.

### 4.3 Pages

| 페이지 | 구현 내용 | 연결 상태 |
|---|---|---|
| Consultation | 메시지/파일 입력 후 대화 생성 | 브라우저 메모리 mock |
| Chat | 메시지 목록, optimistic 메시지, mock AI 응답, 첨부 미리보기 | 백엔드/LLM 미연결 |
| Login/Signup/Verify | JWT 로그인, 가입, 이메일 코드 인증 | FastAPI 연결 |
| Forgot/Reset Password | 재설정 요청, 토큰 검증, 비밀번호 변경 | FastAPI 연결 |
| MyPage | 프로필, 사용량, 모델 선호, 비밀번호 변경, 상담/계정 삭제 | FastAPI 연결 |
| Document/OCR/Search/Evaluation/Admin | 제목 출력 | 기능 미구현 |

### 4.4 Components

| 컴포넌트 | 역할 | 사용 위치 |
|---|---|---|
| `MainLayout` | 공통 Sidebar, 본문, 테마 버튼, 미리보기 배치 | 전체 라우트 |
| `Sidebar` / `HistoryItem` | 대화 목록, 필터/그룹, 생성·이름변경·삭제 | MainLayout |
| `MessageInput` | 텍스트/다중 파일 입력과 모델 선택 | Consultation, Chat |
| `MessageBubble` | 사용자/assistant 메시지와 첨부 표시 | Chat |
| `ModelSelect` | mock 모델 선택 UI | MessageInput |
| `DocumentPreviewPanel` | 첨부파일명과 mock OCR 텍스트 표시/수정 | MainLayout |
| `ThemeToggle` | light/dark 테마 전환 | MainLayout |
| `CursorFxLayer` | 선택한 커서 효과 렌더링 | App |
| `AuthCard` | 인증 페이지 공통 카드 | 인증 페이지들 |
| `ProfileImageUploader` | 이미지 선택 및 R2 업로드 API 호출 | MyPage |
| `PasswordChangeModal` | 비밀번호 변경 | MyPage |
| `ConsultationDeleteModal` | 전체 상담 삭제 | MyPage |
| `AccountDeleteModal` | 비밀번호 확인 후 회원 탈퇴 | MyPage |

### 4.5 CSS / 디자인 관리

- `src/app/styles.css`에서 Tailwind CSS v4를 import하며 다수 화면이 utility class를 직접 사용한다.
- 인증과 마이페이지는 일반 CSS를 함께 사용한다. CSS Module, styled-components는 사용하지 않는다.
- `auth.css`는 인증 카드/폼과 `.dark` 변형을 제공한다.
- `myPage.css`는 `--mypage-*` CSS 변수를 light/dark별로 정의한다. 비밀번호 모달과 프로필 업로더는 별도 CSS 파일을 쓴다.
- `ThemeContext`가 root의 `dark` class와 `localStorage`의 `thegpt-theme`를 관리한다.
- 공통 Button/Input 컴포넌트는 없으며 별도 `assets` 디렉터리도 없다. 커서 이미지는 코드에서 SVG data URL로 만든다.

### 상태 관리, hooks, utils

- 외부 상태 관리 라이브러리 없이 React Context와 내장 hooks를 사용한다.
- 인증 토큰, 테마, 선택 모델, 커서 효과를 `localStorage`에 저장한다. 커서 효과에는 24시간 TTL이 있다.
- 별도 `hooks` 또는 프론트 `utils` 디렉터리는 없다.
- `apiClient`가 JSON 요청, Bearer token, 오류 처리를 공통화한다. 프로필 이미지는 `FormData`용 별도 `fetch`를 쓴다.

## 5. Backend 구조

`backend/app/main.py`의 `app = create_app()`이 진입점이며 `uvicorn app.main:app`으로 실행한다. CORS 설정 후 통합 `api_router`를 `API_PREFIX` 아래에 등록한다.

```text
React → FastAPI Router → Service → Repository
→ SQLAlchemy Session/Model → PostgreSQL 또는 설정된 DB
```

- Router: HTTP 입출력과 dependency 주입
- Service: 인증, 검증, 해시, 메일, 스토리지 비즈니스 규칙
- Repository: SQLAlchemy 조회/저장/삭제
- Schema: Pydantic 요청/응답 타입
- Model: `sqlacodegen`으로 생성된 SQLAlchemy 모델
- Core: DB, 앱, SMTP, R2 설정
- Utils: 현재 구현 없음

### 데이터 모델

| 스키마 | 테이블 | 역할 |
|---|---|---|
| `app_db` | `users` | 사용자, 인증 상태, 프로필 이미지 URL |
| `app_db` | `email_verifications` | 이메일 인증 코드와 만료 시각 |
| `app_db` | `conversations` | 사용자별 상담 메타데이터 |
| `app_db` | `messages` | 대화 메시지 |
| `app_db` | `message_attachments` | 첨부파일 메타데이터 |
| `vector_db` | `admin_documents` | 원문 URL, OCR 텍스트와 처리 상태 |
| `vector_db` | `document_chunks` | 문서 chunk와 1024차원 embedding |

DB에는 상담/RAG용 테이블이 정의되어 있지만 이를 생성·조회하는 API와 서비스는 아직 없다.

### 외부 서비스

- SMTP: 인증 코드와 비밀번호 재설정 링크 발송. SMTP 미설정 개발 환경에는 개발용 코드/URL 응답 분기가 있다.
- Cloudflare R2: JPG/PNG/WEBP, 최대 5MB의 프로필 이미지를 업로드한다.
- JWT: 로그인 access token과 비밀번호 재설정 token에 사용한다.

## 6. AI / OCR / RAG 구조

| 기능 | 위치 | 상태 | 근거 |
|---|---|---|---|
| LLM | `ai/llm/` | 미구현 | `.gitkeep`만 존재 |
| 의료 상담 AI | `ai/consultation/` | 미구현 | `.gitkeep`만 존재; 채팅은 mock |
| 평가 | `ai/evaluation/` | 미구현 | `.gitkeep`만 존재; 화면/라우터도 placeholder |
| OCR | `ai/ocr/` | 미구현 | `.gitkeep`만 존재; 미리보기는 mock 텍스트 |
| RAG | `ai/rag/` | 스키마만 존재 | 코드 디렉터리는 비어 있고 DB 모델만 존재 |
| Embedding | `backend/app/models/generated.py` | 스키마만 존재 | `VECTOR(1024)` 컬럼만 존재 |
| Vector DB | PostgreSQL `vector_db` | 스키마만 존재 | 문서/chunk 모델과 migration만 존재 |
| MedGemma/Gemma/Qwen/Llama | `modelOptions.ts` | UI만 존재 | 선택값만 저장하고 provider 호출 없음 |
| Prompt/Fine-tuning/Ollama | 해당 파일 없음 | 미구현 | 구현 코드가 없음 |

현재 `React → FastAPI → AI Service → LLM` 흐름은 구현되어 있지 않다.

## 7. API 구조

FastAPI의 기본 prefix는 `/api`다. 아래는 실제 decorator가 존재하는 endpoint만 정리했다.

| Method | Endpoint | Frontend 호출 위치 | 목적 |
|---|---|---|---|
| GET | `/health` | 없음 | 앱 상태 확인 |
| GET | `/health/db` | 없음 | DB 연결 확인 |
| POST | `/api/auth/signup` | `signupApi.ts` | 회원가입/인증 코드 발급 |
| POST | `/api/auth/verify-email` | `verificationApi.ts` | 이메일 인증 |
| POST | `/api/auth/resend-verification` | `verificationApi.ts` | 인증 코드 재발송 |
| POST | `/api/auth/login` | `authApi.ts` | 로그인/JWT 발급 |
| GET | `/api/auth/me` | `authApi.ts` | 현재 사용자 조회 |
| POST | `/api/auth/forgot-password` | `passwordResetApi.ts` | 재설정 링크 요청 |
| POST | `/api/auth/validate-reset-token` | `passwordResetApi.ts` | 재설정 token 검증 |
| POST | `/api/auth/reset-password` | `passwordResetApi.ts` | 비밀번호 재설정 |
| POST | `/api/auth/change-password` | `passwordChangeApi.ts` | 비밀번호 변경 |
| POST | `/api/auth/profile/image` | `profileImageApi.ts` | 프로필 이미지 업로드 |
| GET | `/api/auth/me/usage` | `myPageApi.ts` | 상담 수/최근 상담일 조회 |
| DELETE | `/api/auth/me/consultations` | `myPageApi.ts` | 상담 전체 삭제 |
| DELETE | `/api/auth/me` | `myPageApi.ts` | 회원 탈퇴 |

`/api/documents`, `/api/consultation`, `/api/admin`, `/api/evaluations` Router는 등록됐지만 각 파일에 endpoint가 없다.

### Frontend API 구성

- `VITE_API_URL`이 있으면 해당 값을, 없으면 `http://localhost:8000/api`를 사용한다.
- 인증 JSON API는 `services/apiClient.ts`를 공유한다.
- 채팅의 `conversations.ts`, `messages.ts`, `mockStore.ts`는 network 요청 없이 모듈 메모리를 수정한다.
- 새로고침 시 mock 데이터는 초기화되며 DB의 대화/메시지 테이블과 연결되지 않는다.

### 환경변수 이름

실제 값은 제외하고 코드와 `.env.example`에서 확인한 이름만 기록한다.

```text
Frontend: VITE_API_URL

Backend: APP_NAME, APP_ENV, API_PREFIX, CORS_ORIGINS, DATABASE_URL,
MODEL_SCHEMAS, JWT_SECRET_KEY, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES,
PASSWORD_RESET_EXPIRE_MINUTES, FRONTEND_URL,
EMAIL_VERIFICATION_EXPIRE_MINUTES, SMTP_HOST, SMTP_PORT, SMTP_USERNAME,
SMTP_PASSWORD, SMTP_FROM_EMAIL, SMTP_USE_TLS,
R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME,
R2_PUBLIC_URL
```

## 8. 주요 데이터 흐름

### 인증

```text
사용자 입력 → React 인증 Page → apiClient → FastAPI auth Router
→ Auth/Signup Service → Repository → users/email_verifications
→ JWT 또는 인증 결과 → AuthContext → 화면
```

### 프로필 이미지

```text
파일 선택 → React FormData → FastAPI Profile Router
→ 형식/크기 검증 → R2StorageService → Cloudflare R2
→ URL을 users.profile_image_url에 저장 → 사용자 상태 갱신
```

### 현재 채팅

```text
사용자 입력 → React ConsultationPage → 메모리 mock 대화 생성
→ ChatPage → 메모리 mock 메시지 저장 → 규칙 기반 mock assistant 응답
```

LLM, OCR, embedding, vector 검색은 이 흐름에 포함되지 않는다. 첨부파일도 업로드되지 않고 파일명만 mock 메시지에 저장된다.

## 9. 현재 구현 상태

| 영역 | 상태 | 설명 |
|---|---|---|
| SPA 라우팅/공통 레이아웃 | 구현 완료 | 전체 route와 Context 구성 |
| Light/Dark 테마 | 구현 완료 | localStorage와 root `dark` class 사용 |
| JWT 로그인/회원가입/이메일 인증 | 구현 완료 | FastAPI, DB, SMTP 연결 |
| 비밀번호 변경/재설정 | 구현 완료 | 비밀번호 검증과 JWT 재설정 token |
| 마이페이지/계정 삭제 | 구현 완료 | 사용량, 상담 삭제, 회원 탈퇴 |
| 프로필 이미지 | 구현 완료(설정 필요) | R2 환경변수가 있어야 업로드 가능 |
| 상담/채팅 화면 | 개발 중 | UI와 mock 동작만 존재 |
| 대화/메시지 DB | 파일만 존재 | ORM/migration은 있으나 API 미연결 |
| 문서/OCR/검색/평가/관리자 | 개발 초기 | 제목과 빈 FastAPI Router만 존재 |
| RAG/Embedding/Vector DB | 파일만 존재 | DB 모델/migration만 존재 |
| AI 모델 연동 | 미구현 | 모델 선택 UI만 존재 |
| 테스트 | 미구현 | Playwright 의존성만 있고 테스트/스크립트 없음 |

## 10. 이후 작업 시 참고사항

1. 채팅은 `mockStore`에 직접 의존하므로 실제 백엔드 연동으로 오해하지 않아야 한다.
2. Vite 프록시는 `/api/v1`만 대상으로 하지만 `apiClient`와 FastAPI 기본 prefix는 `/api`다. 상대 URL을 쓸 계획이면 세 설정을 일치시켜야 한다.
3. `MainLayout`이 모든 페이지의 부모라 인증 화면에도 Sidebar가 표시된다. 레이아웃 분리 시 route 계층과 Context 범위를 함께 검토해야 한다.
4. `/admin`은 인증/관리자 guard가 없다.
5. 모델 선택값은 UI/localStorage에만 반영되고 메시지 요청에는 전달되지 않는다.
6. 첨부는 DICOM 확장자를 프론트에서 제외하고 일반 이미지는 경고만 표시한다. 실제 MIME 검증, 업로드, OCR은 백엔드에 없다.
7. 기본 SQLite URL과 PostgreSQL 전용 schema/vector 모델은 그대로 호환되지 않을 수 있어 로컬 DB 전략을 정해야 한다.
8. 생성 모델의 `document_chunks`와 `admin_documents` 관계는 서로 다른 schema를 참조하므로 실제 DB 환경에서 FK 동작을 검증해야 한다.
9. 소스 주석과 UI 문구 일부는 현재 표시 환경에서 인코딩이 깨져 보인다. 문구 수정 전 UTF-8 상태를 확인해야 한다.
10. 공통 Button/Input 없이 Tailwind와 일반 CSS가 혼용된다. 디자인 확장 전에 재사용 범위와 스타일 기준을 정하는 것이 안전하다.
