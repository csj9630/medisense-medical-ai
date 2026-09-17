// 메시지/대화 목록에 쓰는 날짜 포맷 — 오늘이면 시각만, 아니면 날짜까지 같이 보여준다.
function isSameDay(a: Date, b: Date) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

export function formatMessageTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';

  const now = new Date();
  const time = date.toLocaleTimeString('ko-KR', { hour: 'numeric', minute: '2-digit' });
  if (isSameDay(date, now)) return time;

  const dateLabel = date.toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric' });
  return `${dateLabel} ${time}`;
}

// 사이드바 대화 목록용 — "방금", "3시간 전", "8월 20일"처럼 상대적으로 짧게 보여준다.
export function formatRelativeDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';

  const diffMs = Date.now() - date.getTime();
  const diffMinutes = Math.floor(diffMs / (60 * 1000));
  if (diffMinutes < 1) return '방금';
  if (diffMinutes < 60) return `${diffMinutes}분 전`;

  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}시간 전`;

  const now = new Date();
  const sameYear = date.getFullYear() === now.getFullYear();
  return date.toLocaleDateString('ko-KR', sameYear ? { month: 'long', day: 'numeric' } : { year: 'numeric', month: 'long', day: 'numeric' });
}
