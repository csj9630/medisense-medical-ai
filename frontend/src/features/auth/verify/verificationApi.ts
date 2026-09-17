import { apiClient } from '../../../services/apiClient';
import type { MessageResponse } from '../signup/signupApi';

export const verificationApi = {
  verifyEmail: (email: string, code: string) =>
    apiClient<MessageResponse>('/auth/verify-email', {
      method: 'POST',
      body: JSON.stringify({ email, code }),
    }),
  resendVerification: (email: string) =>
    apiClient<MessageResponse>('/auth/resend-verification', {
      method: 'POST',
      body: JSON.stringify({ email }),
    }),
};
