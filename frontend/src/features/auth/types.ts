export interface User {
  id: string;
  email: string;
  profile_image_url: string | null;
  is_email_verified: boolean;
  is_admin: boolean;
  created_at: string | null;
  // 소셜 로그인(구글/깃허브)·게스트 계정은 비밀번호가 없다 - 마이페이지가 이
  // 값으로 "비밀번호 변경" 메뉴와 탈퇴 시 비밀번호 입력란을 보여줄지 정한다.
  has_password: boolean;
}

export interface LoginResponse {
  access_token: string;
  token_type: 'bearer';
  user: User;
}

export interface LinkGuestHistoryResponse {
  linked_conversation_count: number;
}
