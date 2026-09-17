# Bruno API 테스트 가이드

Bruno는 Postman과 비슷한 API 테스트 도구인데, 컬렉션이 그냥 텍스트 파일(`.bru`)이라
이렇게 git으로 같이 관리할 수 있어요. 이 폴더가 컬렉션 그 자체입니다.

## 1. 설치 & 열기

1. https://www.usebruno.com 에서 설치 (또는 `winget install Bruno.Bruno`).
2. Bruno 실행 → **Open Collection** → 이 `backend/bruno` 폴더 선택.
3. 왼쪽에 `Auth`, `Conversations` 폴더가 보이면 정상.

## 2. 환경(Environment) 선택

오른쪽 위에 환경 드롭다운이 있어요 (기본은 "No Environment"). **Local**로 바꿔주세요.
`baseUrl`이 `http://localhost:8000/api`로 이미 세팅되어 있어서, 로컬 백엔드만 띄워두면
바로 씁니다:

```bash
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload
```

## 3. 순서대로 실행하면 됩니다

각 요청 파일 이름 앞에 붙은 숫자가 실행 순서예요. **토큰/대화 id를 직접 복사해서
붙여넣을 필요가 없습니다** — 아래 요청들은 응답을 받으면 자동으로 환경변수에
저장하도록 스크립트가 걸려 있어요 (요청 파일을 열어서 `docs` 탭을 보면 뭐가
저장되는지 설명이 있습니다).

**로그인 없이 채팅만 빨리 테스트하고 싶다면:**
```
Auth / 01 Guest Session          → token 자동 저장
Conversations / 01 Create Conversation → conversationId 자동 저장
Conversations / 03 Send Message
Conversations / 04 List Messages
```

**실제 회원가입 → 로그인 흐름까지 테스트하고 싶다면:**
```
Auth / 02 Signup                 → verificationCode 자동 저장 (SMTP 미설정 시)
Auth / 03 Verify Email
Auth / 05 Login                  → token 자동 저장
Auth / 06 Me                     → 내가 로그인한 계정 맞는지 확인
```

비밀번호 재설정(`07~09`)만 예외로, `dev_reset_url`에서 토큰을 눈으로 보고 직접
복사해서 붙여넣어야 해요 (URL 파싱까지는 자동화하지 않았습니다).

## 4. 환경변수가 지금 뭐가 들어있는지 보고 싶다면

오른쪽 위 환경 드롭다운 옆의 눈 모양(또는 설정) 아이콘 → **Local** 클릭하면
`token`, `conversationId`, `verificationCode`가 지금 어떤 값인지 바로 보이고,
필요하면 수동으로 고쳐도 됩니다.

## 5. 배포된 백엔드로 테스트하고 싶을 때

`Local` 환경을 복제해서 `baseUrl`만 배포 주소로 바꾼 새 환경을 만들면 됩니다
(예: `Staging`). 나머지 요청들은 그대로 재사용 가능해요.

## 참고

- 게스트 토큰(`Guest Session`)은 하루 15개 메시지 제한이 있습니다 — 16번째부터
  `429`가 나오면 정상입니다.
- `Send Message`의 assistant 응답은 아직 AI가 아니라 고정 문구입니다
  (`ai/consultation` 연동 전까지).
