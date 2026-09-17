# 비밀번호 재설정

## 처리 흐름

1. 사용자가 로그인 화면에서 `비밀번호를 잊으셨나요?`를 선택합니다.
2. `POST /api/auth/forgot-password`에 가입 이메일을 전송합니다.
3. 가입된 계정이면 백엔드가 30분 동안 유효한 서명 토큰과 재설정 URL을 만듭니다.
4. SMTP를 통해 `/reset-password?token=...` 링크를 발송합니다.
5. 사용자가 새 비밀번호를 입력하면 `POST /api/auth/reset-password`가 토큰을 검증합니다.
6. 새 비밀번호는 Argon2로 해시되어 저장됩니다.
7. 토큰에는 기존 비밀번호의 지문이 포함되므로 변경 후 같은 링크를 다시 사용할 수 없습니다.

가입되지 않은 이메일에도 같은 안내 문구를 반환해 계정 존재 여부가 노출되지 않습니다.

## 환경변수

```env
FRONTEND_URL=http://localhost:5173
PASSWORD_RESET_EXPIRE_MINUTES=30
JWT_SECRET_KEY=충분히-긴-임의의-비밀키
```

실제 이메일 발송에는 `docs/email-verification.md`와 동일한 SMTP 설정을 사용합니다.
로컬에서 SMTP를 설정하지 않으면 API 응답의 `dev_reset_url`로 기능을 테스트할 수 있습니다.
