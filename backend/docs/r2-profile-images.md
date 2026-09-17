# R2 프로필 이미지 설정

## 1. R2 버킷 준비

Cloudflare 대시보드에서 R2 버킷을 생성하고 API 토큰에 해당 버킷의 Object Read & Write 권한을 부여합니다.

프로필 이미지 URL을 브라우저에서 표시하려면 버킷에 다음 중 하나가 필요합니다.

- 운영 환경: R2 커스텀 도메인
- 개발 환경: 공개 `r2.dev` URL

## 2. 백엔드 환경변수

```env
R2_ACCOUNT_ID=cloudflare-account-id
R2_ACCESS_KEY_ID=r2-access-key-id
R2_SECRET_ACCESS_KEY=r2-secret-access-key
R2_BUCKET_NAME=profile-images
R2_PUBLIC_URL=https://assets.example.com
```

`R2_PUBLIC_URL`에는 버킷에 연결한 커스텀 도메인 또는 공개 `r2.dev` URL을 입력합니다.
비밀 키는 `.env` 또는 Cloud Run Secret으로만 관리하고 Git에 커밋하지 않습니다.

## 업로드 규칙

- 허용 형식: JPG, PNG, WEBP
- 최대 크기: 5MB
- 저장 경로: `profiles/{user_id}/{uuid}.{extension}`
- 업로드 후 공개 URL이 Neon `users.profile_image_url`에 저장됩니다.
