import { useEffect, useState, type ReactNode } from 'react';
import { authApi } from './authApi';
import { AuthContext } from './AuthContext';
import { authStorage } from './authStorage';
import { clearGuestSession, getCachedGuestToken } from './guestSession';
import type { User } from './types';

// 로그인 직전까지 게스트로 대화한 이력이 있으면 방금 로그인한 계정으로 옮긴다.
// 게스트로 대화한 적이 없거나(토큰 없음) 이관 자체가 실패해도(토큰 만료 등)
// 로그인 흐름을 막으면 안 되므로 에러는 조용히 무시한다 - 실패하면 그냥 게스트
// 이력이 안 옮겨질 뿐, 로그인은 정상적으로 끝난다.
async function linkGuestHistoryIfAny(token: string): Promise<void> {
  const guestToken = getCachedGuestToken();
  if (!guestToken) return;
  try {
    await authApi.linkGuestHistory(token, guestToken);
  } catch {
    // 무시 - 위 주석 참고
  } finally {
    clearGuestSession();
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const token = authStorage.getToken();
    if (!token) {
      setIsLoading(false);
      return;
    }

    // 새로고침 시 저장된 토큰을 서버에서 검증합니다.
    authApi.getMe(token)
      .then(setUser)
      .catch(() => authStorage.clearToken())
      .finally(() => setIsLoading(false));
  }, []);

  const login = async (email: string, password: string) => {
    const result = await authApi.login(email, password);
    await linkGuestHistoryIfAny(result.access_token);
    authStorage.setToken(result.access_token);
    setUser(result.user);
  };

  const loginWithToken = async (token: string) => {
    const me = await authApi.getMe(token);
    await linkGuestHistoryIfAny(token);
    authStorage.setToken(token);
    setUser(me);
  };

  const logout = () => {
    authStorage.clearToken();
    setUser(null);
  };

  const updateUser = (nextUser: User) => setUser(nextUser);

  return (
    <AuthContext.Provider value={{ user, isLoading, login, loginWithToken, logout, updateUser }}>
      {children}
    </AuthContext.Provider>
  );
}
