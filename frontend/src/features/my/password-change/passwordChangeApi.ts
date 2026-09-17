import { apiClient } from '../../../services/apiClient';
import { authStorage } from '../../auth/authStorage';

interface ChangePasswordResponse {
  message: string;
}

export function changePassword(
  currentPassword: string,
  newPassword: string,
  newPasswordConfirm: string,
) {
  return apiClient<ChangePasswordResponse>('/auth/change-password', {
    method: 'POST',
    token: authStorage.getToken(),
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
      new_password_confirm: newPasswordConfirm,
    }),
  });
}
