const TOKEN_KEY = 'thegpt_access_token';

// 토큰 저장 로직을 한 파일에 모아 나중에 저장 방식을 바꾸기 쉽게 합니다.
export const authStorage = {
  getToken: () => localStorage.getItem(TOKEN_KEY),
  setToken: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clearToken: () => localStorage.removeItem(TOKEN_KEY),
};
