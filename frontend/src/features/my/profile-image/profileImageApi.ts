import { authStorage } from '../../auth/authStorage';
import type { User } from '../../auth/types';

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api';

export async function uploadProfileImage(file: File): Promise<User> {
  const formData = new FormData();
  formData.append('file', file);

  // FormData의 Content-Type과 boundary는 브라우저가 자동으로 설정해야 합니다.
  const response = await fetch(`${API_URL}/auth/profile/image`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${authStorage.getToken() ?? ''}` },
    body: formData,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? '프로필 이미지 업로드에 실패했습니다.');
  }
  return response.json() as Promise<User>;
}
