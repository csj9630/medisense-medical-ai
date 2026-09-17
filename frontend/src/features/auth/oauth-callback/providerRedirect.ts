export const PROVIDER_CALLBACK_PATHS = [
  "/auth/google/callback",
  "/oauth/github/callback",
] as const;

// OAuth code/state를 변경하지 않고 설정된 API 서버로 전달한다.
// 목적지 호스트는 쿼리 입력이 아니라 VITE_API_URL에서만 가져온다.
export function providerCallbackUrl(callbackUrl: string, apiUrl: string): string {
  const callback = new URL(callbackUrl);
  if (!PROVIDER_CALLBACK_PATHS.some((path) => path === callback.pathname)) {
    throw new Error("지원하지 않는 소셜 로그인 콜백입니다.");
  }
  const backend = new URL(apiUrl, callback.origin);
  const target = new URL(callback.pathname, backend.origin);
  target.search = callback.search;
  if (target.origin === callback.origin) {
    throw new Error("소셜 로그인 콜백에는 별도 API 서버 주소가 필요합니다.");
  }
  return target.href;
}
