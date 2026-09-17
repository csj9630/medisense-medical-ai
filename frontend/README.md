# Frontend

Vite, React, TypeScript 기반 프론트엔드입니다.

```bash
npm install
npm run dev
```

실제 환경변수는 프로젝트 최상위 `.env`에서 관리합니다. `frontend/.env.example`은 Frontend 협업자를 위한 `VITE_API_URL` 예시로 유지합니다. Frontend에 공개 가능한 값만 `VITE_` 접두사를 사용하며, `GEMINI_API_KEY` 같은 Backend 비밀값은 Vite 번들에 포함하지 않습니다.

메인 채팅은 Backend LLM Catalog에서 모델 목록을 읽고 선택한
`model_id`를 대화 메시지 API로 전달합니다. 전체 연동 순서와 모델 추가
방법은 `docs/3_flow/12_FLW_MainLLM_메인페이지연동가이드_20260831.md`를 참고합니다.
# 소셜 로그인 콜백 설정

백엔드 배포 환경의 `FRONTEND_URL`을 프론트 도메인으로 설정합니다.
`GOOGLE_OAUTH_REDIRECT_URI`와 `GITHUB_OAUTH_REDIRECT_URI`는 생략하거나 빈 값으로 두면
각각 `FRONTEND_URL/auth/google/callback`, `FRONTEND_URL/oauth/github/callback`으로 자동 생성됩니다.
로컬 개발처럼 별도 콜백 주소가 필요할 때만 두 변수를 명시합니다.

Google·GitHub 개발자 콘솔에도 해당 프론트 콜백 주소를 등록해야 합니다.
이 콘솔 설정은 애플리케이션에서 자동 변경되지 않습니다.

프론트 콜백 라우트는 인증 응답의 쿼리를 보존하여 `VITE_API_URL`의 서버에 있는
동일한 콜백 경로로 전체 페이지를 이동시킵니다. `VITE_API_URL`에는 프론트와 다른
백엔드 주소(예: `https://backend.example/api`)를 지정합니다.
백엔드가 인증 코드를 교환한 뒤 `FRONTEND_URL/oauth-callback`으로 돌려보냅니다.

콜백 전달 테스트: Node.js 22.18 이상에서 `node --test tests/oauth-provider-redirect.test.mjs`.
