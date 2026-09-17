// 서버 응답이 오기 전, 낙관적 렌더링용 임시 id를 만들 때 쓴다.
export function generateId(prefix: string) {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}
