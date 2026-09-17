# 이메일 인증 설정

## 동작 흐름

1. 프론트엔드가 `POST /api/auth/signup`으로 이메일과 비밀번호를 보냅니다.
2. 백엔드는 비밀번호를 Argon2로 해시해 `app_db.users`에 저장합니다.
3. 6자리 인증 코드를 생성해 `app_db.email_verifications`에 10분 만료로 저장합니다.
4. SMTP가 설정돼 있으면 사용자 이메일로 코드를 전송합니다.
5. 사용자가 코드를 입력하면 `POST /api/auth/verify-email`에서 코드와 만료 시간을 확인합니다.
6. 인증에 성공하면 `users.is_email_verified`가 `true`로 변경됩니다.
7. 인증된 사용자만 로그인할 수 있습니다.

## SMTP 환경변수

프로젝트 최상위 `.env`에 사용하는 메일 서비스의 SMTP 정보를 입력합니다.
최상위 `.env`가 없으면 `backend/.env`를 읽습니다. 변경 후 백엔드를 재시작합니다.

```env
APP_ENV=production
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your-smtp-username
SMTP_PASSWORD=your-smtp-password
SMTP_FROM_EMAIL=no-reply@example.com
SMTP_USE_TLS=true
SMTP_USE_SSL=false
SMTP_TIMEOUT_SECONDS=30
```

메일 서비스에서 제공하는 SMTP 호스트, 포트, 사용자명과 비밀번호를 사용해야 합니다.
개인 이메일 계정을 사용할 경우 일반 로그인 비밀번호 대신 앱 비밀번호가 필요할 수 있습니다.

## Cloudflare Email Sending — medisense.ai.kr

1. Cloudflare에서 도메인 상태가 Active인지 확인합니다. 도메인 구매와 네임서버 등록만으로
   Email Sending이 활성화되지는 않습니다.
2. `Compute → Email Service → Email Sending → Onboard Domain`에서 `medisense.ai.kr`을
   선택하고 제공되는 SPF, DKIM, DMARC 및 반송용 MX 레코드를 확인한 뒤 활성화합니다.
3. 해당 Cloudflare 계정의 `Email Sending: Edit` 권한을 가진 API 토큰을 준비합니다.
4. 백엔드 환경변수를 다음과 같이 설정합니다. API 토큰은 `SMTP_PASSWORD`에만 저장하고
   프론트엔드 환경변수나 Git에 넣지 않습니다.

```env
SMTP_HOST=smtp.mx.cloudflare.net
SMTP_PORT=465
SMTP_USERNAME=api_token
SMTP_PASSWORD=<Cloudflare Email Sending API token>
SMTP_FROM_EMAIL=noreply@medisense.ai.kr
SMTP_USE_TLS=false
SMTP_USE_SSL=true
SMTP_TIMEOUT_SECONDS=30
```

Cloudflare는 465번 포트의 implicit TLS를 사용합니다. `SMTP_USE_TLS`는 STARTTLS 옵션이므로
위 설정에서는 끄고 `SMTP_USE_SSL`을 켭니다. 인증 코드와 비밀번호 재설정 메일 모두 이 연결을 사용합니다.
사용자명만 있고 토큰이 비어 있으면 아직 발송 설정이 완료되지 않은 것으로 처리합니다.

운영 서버에는 동일한 SMTP 설정과 `APP_ENV=production`을 배포 Secret으로 적용해야 합니다.
로컬 파일 변경만으로 운영 서버 설정이 바뀌지는 않습니다. 등록과 토큰 설정 후 테스트 계정으로
회원가입 → 메일 수신 → 코드 검증 → 로그인을 확인합니다.

공식 문서: [SMTP 설정](https://developers.cloudflare.com/email-service/api/send-emails/smtp/),
[도메인 등록](https://developers.cloudflare.com/email-service/get-started/send-emails/).

## 로컬 개발

SMTP 값을 비워두고 `APP_ENV=local`로 실행하면 메일을 보내지 않고 회원가입 API 응답에
`dev_verification_code`가 포함됩니다. 프론트엔드는 이 값을 인증 화면에 표시합니다.

운영 환경에서는 반드시 다음을 지켜야 합니다.

- `APP_ENV=production`으로 설정합니다.
- 충분히 긴 임의 문자열을 `JWT_SECRET_KEY`에 사용합니다.
- `.env`를 Git에 커밋하지 않습니다.
- SMTP 인증 정보는 배포 환경의 Secret으로 관리합니다.

## 2026-09-10 서버 적용 기록

- 접속 주소: https://medisense.ai.kr
- 기존 Cloud Run: `the-gpt-dev` 프로젝트 / `asia-northeast3` / `the-gpt-dev` 서비스
- 이메일 적용 리비전: `the-gpt-dev-00037-wuq`
- 이전 리비전: `the-gpt-dev-00036-mxb`
- Cloudflare Worker: `thegpt-project`, 적용 버전 `f6271a0e` (dev 소스 `c7ede19`)
- Secret Manager: `medisense-email-smtp-token:1`을 `SMTP_PASSWORD`로 참조
- `APP_ENV=production`, `FRONTEND_URL=https://medisense.ai.kr`
- CORS에 `https://medisense.ai.kr`, `https://thegpt-project.thegpt.workers.dev` 추가
- Google/GitHub 콜백은 기존 공급자 등록과 호환되도록 각각
  `https://dev-thegpt-project.thegpt.workers.dev/auth/google/callback`,
  `https://dev-thegpt-project.thegpt.workers.dev/oauth/github/callback`을 명시한다.
  콜백 처리가 끝나면 새 `FRONTEND_URL`의 화면으로 이동한다.
- 토큰 값은 소스에 포함하지 않는다. 서비스 계정에는 위 Secret 하나의 읽기 권한만 부여했다.

서버에는 기존 실행 이미지 위에 이메일 설정·발송 코드만 추가한 이미지를 배포했다.
다음 소스 기반 배포에서도 메일 발송을 유지하려면 이 SMTP SSL 코드 변경을 포함해야 한다.
`frontend/wrangler.jsonc`에도 사용자 지정 도메인을 명시했다.

확인: 새 리비전과 대표 서비스 URL의 health 및 DB 연결, 새 도메인 CORS preflight,
OAuth authorize의 기존 callback URI, 실제 비밀번호 재설정 메일 발송 API(개발용 URL 미노출).
