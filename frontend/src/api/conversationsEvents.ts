// Sidebar와 ChatPage는 형제 트리라 서로 상태를 직접 못 본다. 첫 메시지 전송으로
// 대화 제목이 자동으로 바뀌는 것처럼, ChatPage가 대화 메타데이터를 바꾼 뒤 Sidebar가
// 목록을 다시 불러오게 하려고 쓰는 아주 얇은 pub-sub.
type Listener = () => void;
const listeners = new Set<Listener>();

export function onConversationsChanged(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function notifyConversationsChanged(): void {
  listeners.forEach((listener) => listener());
}
