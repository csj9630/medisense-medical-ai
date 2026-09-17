import { ApiError, apiClient } from '../../services/apiClient';
import { authStorage } from './authStorage';
import type { LoginResponse } from './types';

const GUEST_TOKEN_KEY = 'thegpt_guest_token';
const GUEST_DISPLAY_ID_KEY = 'thegpt_guest_display_id';

let inFlight: Promise<string> | null = null;

/**
 * 사이드바 하단에 보여줄 "게스트_123456" 같은 표시용 이름.
 * 실제 유저 id와는 무관한 순전히 화면 표시용 랜덤 숫자(6자리) — 한 번 만들면 이
 * 브라우저에서는 계속 같은 값을 쓴다 (게스트 토큰 로딩을 기다릴 필요 없이 동기적으로
 * 바로 쓸 수 있음).
 */
export function getGuestDisplayName(): string {
  let displayId = localStorage.getItem(GUEST_DISPLAY_ID_KEY);
  if (!displayId) {
    displayId = String(Math.floor(100000 + Math.random() * 900000));
    localStorage.setItem(GUEST_DISPLAY_ID_KEY, displayId);
  }
  return `게스트_${displayId}`;
}

/**
 * 로그인 직후(AuthProvider) 게스트 대화 이력 이관에 쓰기 위한, 저장된 게스트
 * 토큰 조회. 새로 발급받지 않고 캐시된 값만 본다 - 게스트로 대화한 적이 없으면
 * null.
 */
export function getCachedGuestToken(): string | null {
  return localStorage.getItem(GUEST_TOKEN_KEY);
}

/** 게스트 이력 이관을 마친 뒤(또는 시도 자체가 필요 없을 때) 게스트 세션 흔적을 지운다. */
export function clearGuestSession(): void {
  localStorage.removeItem(GUEST_TOKEN_KEY);
  localStorage.removeItem(GUEST_DISPLAY_ID_KEY);
}

function requestGuestToken(): Promise<string> {
  if (!inFlight) {
    inFlight = apiClient<LoginResponse>('/auth/guest', { method: 'POST' })
      .then((response) => {
        localStorage.setItem(GUEST_TOKEN_KEY, response.access_token);
        return response.access_token;
      })
      .finally(() => {
        inFlight = null;
      });
  }
  return inFlight;
}

/**
 * 채팅 API 호출에 쓸 토큰을 가져온다.
 * 로그인한 사용자는 자신의 토큰을, 아니면 서버가 발급하는 게스트 토큰을 브라우저에
 * 오래 캐시해두고 재사용한다 (재방문 시 같은 게스트 계정으로 이어짐).
 * mypage 등 실제 로그인이 필요한 화면과는 무관 — AuthContext.user는 건드리지 않는다.
 */
export async function getChatToken(): Promise<string> {
  const userToken = authStorage.getToken();
  if (userToken) return userToken;

  const cachedGuestToken = localStorage.getItem(GUEST_TOKEN_KEY);
  if (cachedGuestToken) return cachedGuestToken;

  return requestGuestToken();
}

/**
 * 채팅 API 호출을 감싸서, 캐시해둔 게스트 토큰이 더 이상 유효하지 않을 때
 * (게스트 계정 만료/서버측 정리 등으로 401이 나는 경우) 자동으로 새 게스트
 * 세션을 발급받아 한 번 재시도한다. 로그인한 사용자의 토큰이 만료된 경우는
 * 여기서 조용히 게스트로 전환시키지 않고 그대로 에러를 올린다 (재로그인 유도).
 */
export async function withChatToken<T>(call: (token: string) => Promise<T>): Promise<T> {
  const token = await getChatToken();
  try {
    return await call(token);
  } catch (error) {
    const isGuestToken = !authStorage.getToken();
    if (isGuestToken && error instanceof ApiError && error.status === 401) {
      localStorage.removeItem(GUEST_TOKEN_KEY);
      const freshToken = await requestGuestToken();
      return call(freshToken);
    }
    throw error;
  }
}
