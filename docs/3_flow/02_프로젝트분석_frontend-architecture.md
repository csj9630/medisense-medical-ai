# Frontend Architecture — TheGPT Project

> 분석 기준일: 2026-08-14
> 분석 대상: `frontend/` 디렉터리 전체 (READ ONLY — 코드 변경 없음)

---

## 1. Frontend 전체 디렉터리 구조

```
frontend/
├── index.html                      # Vite SPA 진입 HTML
├── vite.config.ts                  # Vite + TailwindCSS v4 설정, dev proxy 설정
├── package.json                    # 의존성 (React 19, React Router v7, lucide-react, Tailwind v4)
├── tsconfig.json
└── src/
    ├── main.tsx                    # ReactDOM.createRoot() — 앱 최초 진입점
    ├── global.d.ts
    ├── app/
    │   ├── App.tsx                 # Provider 트리 조립 + RouterProvider
    │   ├── router.tsx              # createBrowserRouter — 전체 라우트 정의
    │   └── styles.css              # 전역 CSS (Tailwind import 포함)
    │
    ├── components/                 # 공통/재사용 컴포넌트
    │   ├── Chat/
    │   │   ├── MessageInput.tsx        # 파일 첨부 + 텍스트 입력 + 전송 폼
    │   │   ├── MessageBubble.tsx       # 대화 말풍선 (user/assistant 구분)
    │   │   ├── ModelSelect.tsx         # LLM 모델 선택 드롭다운
    │   │   ├── ModelSelectContext.tsx  # 선택된 모델 전역 상태 (localStorage 저장)
    │   │   ├── modelOptions.ts         # 모델 목록 상수 (medgemma, gemma, Qwen, Llama)
    │   │   ├── DocumentPreviewContext.tsx  # 문서 미리보기 패널 상태
    │   │   └── DocumentPreviewPanel.tsx    # 우측 원본/파싱 텍스트 패널 (mock)
    │   ├── Layout/
    │   │   └── MainLayout.tsx      # 사이드바 + main(Outlet) + 문서패널 3단 레이아웃
    │   ├── Sidebar/
    │   │   ├── Sidebar.tsx         # 대화 목록 + 로그인/마이페이지 버튼
    │   │   ├── HistoryItem.tsx     # 개별 대화 항목 (인라인 이름 편집, 삭제)
    │   │   ├── SidebarContext.tsx  # collapsed 상태 Context
    │   │   └── index.ts            # Sidebar, SidebarProvider, useSidebar 재export
    │   ├── Theme/
    │   │   ├── ThemeContext.tsx    # 다크/라이트 모드 Context (localStorage 저장)
    │   │   └── ThemeToggle.tsx    # 우상단 테마 토글 버튼
    │   └── CursorFx/
    │       ├── CursorFxContext.tsx # 이스터에그 커서 효과 상태 (Alt+D/S 단축키)
    │       ├── CursorFxLayer.tsx  # 커서 렌더링 레이어
    │       └── cursorOptions.ts   # 커서 디자인 옵션
    │
    ├── features/                   # 페이지별 기능 단위
    │   ├── auth/
    │   │   ├── AuthContext.tsx     # useAuth 훅 + AuthContextValue 타입
    │   │   ├── AuthProvider.tsx    # 로그인 상태 관리 (토큰 -> getMe 검증)
    │   │   ├── RequireAuth.tsx     # 인증 가드 (미로그인 시 /login 리다이렉트)
    │   │   ├── authApi.ts          # login, getMe API 호출
    │   │   ├── authStorage.ts      # localStorage 토큰 CRUD
    │   │   ├── types.ts            # User, LoginResponse 타입
    │   │   ├── components/
    │   │   │   ├── AuthCard.tsx   # 인증 페이지 공통 카드 레이아웃
    │   │   │   └── auth.css
    │   │   ├── login/index.tsx    # 로그인 폼 페이지
    │   │   ├── signup/
    │   │   │   ├── index.tsx      # 회원가입 폼 페이지
    │   │   │   └── signupApi.ts   # POST /auth/signup
    │   │   ├── verify/
    │   │   │   ├── index.tsx      # 이메일 인증 코드 입력 페이지
    │   │   │   └── verificationApi.ts
    │   │   └── password-reset/
    │   │       ├── ForgotPasswordPage.tsx
    │   │       ├── ResetPasswordPage.tsx
    │   │       └── passwordResetApi.ts
    │   │
    │   ├── consultation/index.tsx  # 홈(/) — 새 대화 시작 화면
    │   ├── chat/index.tsx          # /chat/:conversationId — 채팅 화면
    │   ├── my/
    │   │   ├── index.tsx           # 마이페이지
    │   │   ├── myPageApi.ts        # getUsage, deleteAccount, deleteAllConsultations
    │   │   ├── ModelPreference.tsx # 모델 선호도 설정 UI
    │   │   ├── myPage.css
    │   │   ├── password-change/   # 비밀번호 변경 모달
    │   │   ├── profile-image/     # 프로필 이미지 업로더
    │   │   ├── account-delete/    # 회원 탈퇴 모달
    │   │   └── consultation-delete/ # 상담 데이터 전체 삭제 모달
    │   │
    │   ├── admin/index.tsx         # 모델 성능 비교 대시보드 (stub)
    │   ├── document/index.tsx      # 문서 및 이미지 업로드 (stub)
    │   ├── ocr/index.tsx           # OCR 결과 (stub)
    │   ├── search/index.tsx        # 근거 문서 검색 (stub)
    │   └── evaluation/index.tsx    # 평가 (stub)
    │
    ├── api/                        # 현재 mock 구현 (백엔드 연동 전 in-memory)
    │   ├── conversations.ts        # getConversations, createConversation, rename, delete
    │   ├── messages.ts             # getMessages, sendMessage (mock reply 생성)
    │   ├── mockStore.ts            # 인메모리 대화/메시지 저장소 + mock 데이터
    │   └── types.ts                # Conversation, Message 인터페이스
    │
    ├── services/
    │   └── apiClient.ts            # fetch 래퍼 — Authorization Bearer 헤더 자동 주입
    │
    ├── hooks/                      # (비어 있음, .gitkeep)
    ├── lib/                        # (비어 있음, .gitkeep)
    ├── types/                      # (비어 있음, .gitkeep)
    └── utils/                      # (비어 있음, .gitkeep)
```

---

## 2. React 앱이 실행되는 시작점

```
index.html
  └─ <script type="module" src="/src/main.tsx">
       └─ main.tsx
            createRoot(document.getElementById('root'))
              .render(<StrictMode><App /></StrictMode>)
```

| 파일 | 역할 |
|---|---|
| `index.html` | Vite SPA 껍데기, `<div id="root">` 포함 |
| `src/main.tsx` | `createRoot().render()` — React 트리 시작 |
| `src/app/App.tsx` | Provider 트리 조립 후 `RouterProvider` 마운트 |
| `src/app/styles.css` | 전역 CSS (Tailwind 포함) |

---

## 3. Router / Layout / Page 연결 구조

### Provider 래핑 순서 (App.tsx)

```
ThemeProvider
  └─ AuthProvider
       └─ ModelSelectProvider
            └─ CursorFxProvider
                 ├─ RouterProvider (router)
                 └─ CursorFxLayer
```

### 라우트 트리 (router.tsx)

```
<MainLayout>                         ← 전체 공통 레이아웃
  ├─ /                → ConsultationPage   (홈 — 새 대화 시작)
  ├─ /chat/:id        → ChatPage           (채팅)
  ├─ /login           → LoginPage
  ├─ /signup          → SignupPage
  ├─ /verify-email    → VerifyEmailPage
  ├─ /forgot-password → ForgotPasswordPage
  ├─ /reset-password  → ResetPasswordPage
  ├─ /document        → DocumentPage       (stub)
  ├─ /ocr             → OcrPage            (stub)
  ├─ /search          → SearchPage         (stub)
  ├─ /evaluation      → EvaluationPage     (stub)
  ├─ /admin           → AdminPage          (stub)
  └─ RequireAuth (인증 가드)
       ├─ /mypage     → MyPage
       └─ /my         → MyPage
```

### MainLayout 구조

```
<aside>  Sidebar
<main>   ThemeToggle + <Outlet />   ← 라우트 별 페이지가 여기에 렌더됨
<aside>  DocumentPreviewPanel       ← 파일 클릭 시만 표시
```

---

## 4. 주요 Component 역할

| 컴포넌트 | 파일 경로 | 역할 |
|---|---|---|
| `MainLayout` | `components/Layout/MainLayout.tsx` | 3단 레이아웃(사이드바/본문/문서패널) + Provider 2개 포함 |
| `Sidebar` | `components/Sidebar/Sidebar.tsx` | 대화 목록 + 진료과 필터 + 사용자 영역(로그인/로그아웃) |
| `HistoryItem` | `components/Sidebar/HistoryItem.tsx` | 개별 대화 카드 — 인라인 이름 수정, 삭제 기능 |
| `MessageInput` | `components/Chat/MessageInput.tsx` | 텍스트 + 파일 첨부 입력 폼. DICOM 파일 차단, 이미지 경고 |
| `MessageBubble` | `components/Chat/MessageBubble.tsx` | user/assistant 말풍선. 첨부파일 클릭 시 미리보기 패널 열기 |
| `ModelSelect` | `components/Chat/ModelSelect.tsx` | 입력창 하단 LLM 모델 드롭다운 (medgemma 기본값) |
| `DocumentPreviewPanel` | `components/Chat/DocumentPreviewPanel.tsx` | 파일 원본 + 파싱 텍스트 우측 패널 (현재 mock) |
| `ThemeToggle` | `components/Theme/ThemeToggle.tsx` | 다크/라이트 모드 전환 버튼 |
| `CursorFxLayer` | `components/CursorFx/CursorFxLayer.tsx` | 이스터에그 커서 효과 (Alt+D/S 단축키) |
| `RequireAuth` | `features/auth/RequireAuth.tsx` | 인증 가드 — 미로그인 시 /login 으로 리다이렉트 |
| `AuthCard` | `features/auth/components/AuthCard.tsx` | 인증 관련 페이지 공통 카드 레이아웃 |
| `ConsultationPage` | `features/consultation/index.tsx` | 홈 화면. 메시지 전송 시 대화 생성 후 ChatPage 이동 |
| `ChatPage` | `features/chat/index.tsx` | 채팅 화면. 메시지 로드/전송, optimistic update, 자동 스크롤 |
| `MyPage` | `features/my/index.tsx` | 계정 관리, 이용 현황, 환경설정, 로그아웃/탈퇴 |

---

## 5. Backend API를 호출하는 파일과 방식

### 핵심 클라이언트 — `src/services/apiClient.ts`

```ts
// VITE_API_URL 기본값: http://localhost:8000/api
// dev 환경에서는 vite.config.ts의 proxy가 /api/v1 -> localhost:8000 으로 중계
const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api';

export async function apiClient<T>(path, options): Promise<T> {
  // token이 있으면 Authorization: Bearer {token} 헤더 자동 주입
  // 오류 시 body.detail 메시지를 throw
}
```

### API 파일 목록

| 파일 | 호출 엔드포인트 | 상태 |
|---|---|---|
| `features/auth/authApi.ts` | `POST /auth/login`, `GET /auth/me` | ✅ 실제 연동 |
| `features/auth/signup/signupApi.ts` | `POST /auth/signup` | ✅ 실제 연동 |
| `features/auth/verify/verificationApi.ts` | 이메일 인증 관련 | ✅ 실제 연동 |
| `features/auth/password-reset/passwordResetApi.ts` | 비밀번호 재설정 | ✅ 실제 연동 |
| `features/my/password-change/passwordChangeApi.ts` | 비밀번호 변경 | ✅ 실제 연동 |
| `features/my/myPageApi.ts` | `GET /auth/me/usage`, `DELETE /auth/me`, `DELETE /auth/me/consultations` | ✅ 실제 연동 |
| `api/conversations.ts` | 백엔드 없음 — in-memory mock | ❌ Mock |
| `api/messages.ts` | 백엔드 없음 — in-memory mock | ❌ Mock |

> **패턴 요약**: 인증/계정 관련은 실제 FastAPI 백엔드와 연동.
> 채팅 핵심(대화/메시지)은 아직 mock 단계.

---

## 6. 로그인/인증 관련 구조

### 흐름

```
AuthProvider 마운트 시:
  1. localStorage에서 'thegpt_access_token' 읽기
  2. 토큰 있으면 → authApi.getMe(token) → user 상태 설정
  3. 토큰 없으면 → user = null

로그인 성공 시:
  authApi.login(email, password)
  → { access_token, user } 수신
  → authStorage.setToken(token)  [localStorage 저장]
  → setUser(user)
  → navigate('/')

로그아웃 시:
  authStorage.clearToken()
  → setUser(null)
```

### 핵심 파일

| 파일 | 역할 |
|---|---|
| `AuthContext.tsx` | `AuthContextValue` 타입 정의 + `useAuth()` 훅 제공 |
| `AuthProvider.tsx` | 토큰 검증, login / logout / updateUser 함수 관리 |
| `authStorage.ts` | localStorage 키: `thegpt_access_token` |
| `RequireAuth.tsx` | 로딩 중 대기, user 없으면 `/login` 리다이렉트 |

### User 타입

```ts
interface User {
  id: string;
  email: string;
  profile_image_url: string | null;
  is_email_verified: boolean;
  is_admin: boolean;
  created_at: string | null;
}
```

### 현재 인증 보호 라우트

- 보호됨: `/mypage`, `/my`
- 비보호 (누구나 접근 가능): `/admin`, `/chat/:id`, `/document`, `/ocr`, `/search`, `/evaluation`

---

## 7. 의료 챗봇 화면과 관련된 파일

### 대화 흐름

```
1. 홈(/) — ConsultationPage
   → 사용자가 메시지 입력 + 전송
   → createConversation() 호출 (현재 mock)
   → navigate('/chat/:id', { state: { pendingMessage, pendingFiles } })

2. 채팅(/chat/:id) — ChatPage
   → conversationId 마운트 시 getMessages() 로드
   → pendingMessage가 있으면 즉시 sendUserMessage() 실행
   → optimistic update: 사용자 메시지 즉시 화면에 추가
   → sendMessage() → mock 응답 생성 (600ms 지연)
   → assistant 메시지 추가
```

### 의료 챗봇 관련 핵심 파일

| 파일 | 역할 |
|---|---|
| `features/consultation/index.tsx` | 홈 화면 — 새 대화 생성 진입점 |
| `features/chat/index.tsx` | 실제 채팅 화면 — 메시지 렌더링 및 전송 |
| `components/Chat/MessageInput.tsx` | 입력 폼 — DICOM 차단, 이미지 경고, 모델 선택 포함 |
| `components/Chat/MessageBubble.tsx` | 메시지 말풍선 + 첨부파일 미리보기 버튼 |
| `components/Chat/ModelSelect.tsx` | LLM 모델 선택 드롭다운 |
| `components/Chat/DocumentPreviewPanel.tsx` | 문서 원본 + 파싱 결과 우측 패널 |
| `api/conversations.ts` | 대화 CRUD (현재 mock) |
| `api/messages.ts` | 메시지 로드/전송 (현재 mock) |
| `api/mockStore.ts` | 당뇨/MRI/감기 샘플 대화 데이터 포함 |
| `components/Chat/modelOptions.ts` | 모델 목록: medgemma(추천), gemma, Qwen, Llama |

### 의료 특화 처리

- **DICOM 파일 차단**: `.dcm`, `.dicom` 확장자는 첨부 자체를 막음
- **이미지 경고**: PNG/JPG 등 이미지 첨부 시 "MRI·CT·X-Ray 분석 불가" 경고 표시
- **진료과 카테고리**: 사이드바에서 진료과별 대화 목록 필터링 가능
- **Mock 대화 예시**: 내분비내과(당뇨), 영상의학과(MRI), 가정의학과(감기)

---

## 8. 현재 구현되어 있는 기능

| 기능 | 구현 수준 |
|---|---|
| 로그인 / 로그아웃 | 실제 백엔드 연동. JWT 토큰 localStorage 저장 |
| 회원가입 + 이메일 인증 | 실제 백엔드 연동. 인증 코드 입력 페이지 포함 |
| 비밀번호 찾기 / 재설정 | 실제 백엔드 연동 |
| 마이페이지 — 비밀번호 변경 | 모달 방식, 실제 백엔드 연동 |
| 마이페이지 — 회원 탈퇴 | 실제 백엔드 연동 |
| 마이페이지 — 이용 현황 | `GET /auth/me/usage` 실제 연동 |
| 마이페이지 — 상담 데이터 전체 삭제 | 실제 백엔드 연동 |
| 다크 / 라이트 모드 | localStorage 저장, 즉시 반영 |
| 사이드바 접기 / 펼치기 | Context로 상태 관리 |
| 사이드바 대화 제목 수정 | 인라인 편집 (현재 mock) |
| 사이드바 대화 삭제 | 확인 다이얼로그 후 삭제 (현재 mock) |
| 진료과별 대화 목록 필터 | 카테고리 그룹핑, 접기/펼치기 |
| 채팅 UI — 메시지 입력 / 전송 | 폼, 엔터/Shift+엔터 지원 (mock 응답) |
| 채팅 UI — 파일 첨부 | 복수 파일 선택, DICOM 차단, 이미지 경고 |
| 채팅 UI — 문서 미리보기 패널 | 우측 패널 (mock 텍스트) |
| LLM 모델 선택 드롭다운 | UI + localStorage 저장 (실제 백엔드 연동 없음) |
| Optimistic Update | 메시지 전송 시 즉시 화면 반영 |
| 자동 스크롤 | 새 메시지 추가 시 하단으로 스크롤 |
| 커서 이스터에그 | Alt+D/S 단축키로 커스텀 커서 토글 |
| 프로필 이미지 업로더 | UI 구현됨 |
| 모델 선호도 설정 (마이페이지) | UI 구현됨 |

---

## 9. 아직 구현되지 않았거나 TODO인 부분

### Mock 상태 — 실제 백엔드 연동 필요

| 항목 | 파일 | TODO 내용 |
|---|---|---|
| 대화 생성 | `api/conversations.ts` | `POST /api/v1/conversations` 실제 fetch로 교체 |
| 대화 목록 조회 | `api/conversations.ts` | `GET /api/v1/conversations` 실제 fetch로 교체 |
| 대화 이름 변경 | `api/conversations.ts` | `PATCH /api/v1/conversations/:id` 실제 연동 |
| 대화 삭제 | `api/conversations.ts` | `DELETE /api/v1/conversations/:id` 실제 연동 |
| 메시지 조회 | `api/messages.ts` | `GET /api/v1/conversations/:id/messages` 실제 연동 |
| 메시지 전송 (LLM) | `api/messages.ts` | `POST /api/v1/conversations/:id/messages` 실제 LLM 응답 |
| 모델 선택 백엔드 반영 | `ModelSelectContext.tsx` | 선택된 모델 ID를 메시지 전송 시 백엔드에 전달 |
| 문서 미리보기 패널 | `DocumentPreviewPanel.tsx` | 실제 OCR/파싱 결과 수신, 수정 내용 저장 API 연동 |

### 페이지 자체가 stub 상태

| 페이지 | 경로 | 현재 상태 |
|---|---|---|
| `DocumentPage` | `/document` | `<h1>문서 및 이미지 업로드</h1>` 만 있음 |
| `OcrPage` | `/ocr` | `<h1>OCR 결과</h1>` 만 있음 |
| `SearchPage` | `/search` | `<h1>근거 문서 검색</h1>` 만 있음 |
| `EvaluationPage` | `/evaluation` | `<h1>평가</h1>` 만 있음 |
| `AdminPage` | `/admin` | `<h1>모델 성능 비교 대시보드</h1>` 만 있음 |

### 인증 가드가 없는 라우트

`/admin`, `/chat/:id`, `/document`, `/ocr`, `/search`, `/evaluation` 은
`RequireAuth` 없이 누구나 접근 가능. 필요에 따라 보호 설정 필요.

### 빈 디렉터리 (향후 구현 예정)

- `src/hooks/` — 커스텀 훅 예정
- `src/lib/` — 유틸리티 라이브러리 예정
- `src/types/` — 공통 타입 예정
- `src/utils/` — 유틸 함수 예정

---

## 10. 프론트 담당자라면 우선 봐야 할 파일 5개

| 순위 | 파일 | 이유 |
|---|---|---|
| 1 | `src/app/router.tsx` | 전체 라우트 구조 한눈에 파악. 어디에 무엇이 있는지 지도 역할 |
| 2 | `src/api/conversations.ts` + `messages.ts` | 채팅 핵심 데이터 흐름. TODO 주석이 정확히 무엇을 교체해야 하는지 안내함 |
| 3 | `src/features/chat/index.tsx` | 실제 채팅 로직. optimistic update, pendingMessage, StrictMode 중복 방지 패턴 |
| 4 | `src/features/auth/AuthProvider.tsx` | 로그인 상태 전역 관리. 토큰 검증, login/logout 함수 정의 |
| 5 | `src/services/apiClient.ts` | 모든 실제 API 호출의 기반. VITE_API_URL, Bearer 토큰 주입, 에러 처리 방식 |

---

## 한 줄 흐름도

```
Browser -> React(main.tsx) -> Page(ConsultationPage/ChatPage) -> Service/API(apiClient.ts / mock) -> FastAPI(localhost:8000/api) -> Response
```

### 상세 흐름 — 채팅 메시지 전송 기준

```
Browser (사용자 입력 + 전송)
  -> MessageInput.onSend()
      -> ChatPage.sendUserMessage()
          -> [현재] api/messages.ts (mockStore — in-memory, 600ms 딜레이)
          -> [목표] apiClient('/conversations/:id/messages', POST)
              -> Vite dev proxy (/api/v1 -> localhost:8000)
                  -> FastAPI router -> consultation_router
                      -> LLM 서비스 (medgemma 등)
                          -> Response (Message JSON)
  <- setMessages([...prev, assistantMessage])
  <- MessageBubble 렌더링
```

---

*이 문서는 2026-08-14 기준 코드를 READ ONLY로 분석한 결과입니다. 코드 변경은 일절 없었습니다.*
