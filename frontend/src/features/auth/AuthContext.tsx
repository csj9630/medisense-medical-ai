import { createContext, useContext } from 'react';
import type { User } from './types';

export interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  // OAuth 콜백 페이지 전용 - 이미 백엔드가 발급한 토큰을 그대로 받아서 저장하고
  // /auth/me로 사용자 정보만 채운다(비밀번호 로그인과 달리 여기선 이미 로그인이
  // 끝난 뒤라 인증 요청을 다시 보낼 필요가 없음).
  loginWithToken: (token: string) => Promise<void>;
  logout: () => void;
  updateUser: (user: User) => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth는 AuthProvider 안에서 사용해야 합니다.');
  return context;
}
