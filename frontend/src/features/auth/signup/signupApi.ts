import { apiClient } from '../../../services/apiClient';

export interface MessageResponse {
  message: string;
  dev_verification_code: string | null;
}

export const signupApi = {
  signup: (email: string, password: string) =>
    apiClient<MessageResponse>('/auth/signup', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
};
