import { apiClient } from '../../../services/apiClient';

interface PasswordResetMessage {
  message: string;
  dev_reset_url: string | null;
}

export const passwordResetApi = {
  request: (email: string) => apiClient<PasswordResetMessage>('/auth/forgot-password', {
    method: 'POST', body: JSON.stringify({ email }),
  }),
  reset: (token: string, newPassword: string) => apiClient<PasswordResetMessage>('/auth/reset-password', {
    method: 'POST', body: JSON.stringify({ token, new_password: newPassword }),
  }),
  validate: (token: string) => apiClient<PasswordResetMessage>('/auth/validate-reset-token', {
    method: 'POST', body: JSON.stringify({ token }),
  }),
};
