import { API_URL, apiClient } from '../../services/apiClient';
import type { LinkGuestHistoryResponse, LoginResponse, User } from './types';

export type OAuthProvider = 'google' | 'github';

export const authApi = {
  login: (email: string, password: string) =>
    apiClient<LoginResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  getMe: (token: string) => apiClient<User>('/auth/me', { token }),

  // 게스트로 대화하다 로그인한 직후 호출 - 실패해도(게스트 토큰 만료 등) 로그인
  // 자체를 막으면 안 되므로 호출하는 쪽(AuthProvider)이 에러를 무시한다.
  linkGuestHistory: (token: string, guestToken: string) =>
    apiClient<LinkGuestHistoryResponse>('/auth/link-guest-history', {
      method: 'POST',
      token,
      body: JSON.stringify({ guest_token: guestToken }),
    }),

  // 버튼 클릭 시 이 주소로 풀페이지 이동(window.location.href)한다 - 백엔드가
  // Google/GitHub 동의 화면으로 다시 리다이렉트해준다. fetch가 아니라 브라우저
  // 자체 이동이어야 실제 로그인 화면(팝업 아님)으로 넘어간다.
  oauthLoginUrl: (provider: OAuthProvider) => `${API_URL}/auth/oauth/${provider}/authorize`,
};
