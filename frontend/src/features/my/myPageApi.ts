import { apiClient } from '../../services/apiClient';
import { authStorage } from '../auth/authStorage';

export interface UsageSummary {
  consultation_count: number;
  last_consultation_at: string | null;
}

export const myPageApi = {
  getUsage: () => apiClient<UsageSummary>('/auth/me/usage', { token: authStorage.getToken() }),
  // 소셜 로그인/게스트 계정은 비밀번호가 없어서 생략 가능하다(AccountDeleteModal 참고).
  deleteAccount: (password?: string) => apiClient<{ message: string }>('/auth/me', {
    method: 'DELETE', token: authStorage.getToken(), body: JSON.stringify({ password: password ?? null }),
  }),
  deleteAllConsultations: () => apiClient<{ message: string; deleted_count: number }>(
    '/auth/me/consultations',
    { method: 'DELETE', token: authStorage.getToken() },
  ),
};
