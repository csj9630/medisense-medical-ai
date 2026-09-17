// 커서 디자인 종류. cssCursor는 커서 아이콘, trailGlyph는 마우스 이동 시 남는 잔상 문자.
export type CursorOption = {
  id: string;
  label: string;
  cssCursor: string;
  trailGlyph: string | null;
  trailColor: string;
  // true면 trailGlyph 하나 대신 CHAOS_GLYPHS 풀에서 여러 개를 뽑아 크고 빠르고
  // 무지개색으로 뿌린다 (CursorFxLayer 참고). 존재감을 극대화하려는 용도의 특수 옵션.
  chaos?: boolean;
};

function dotCursorSvg(color: string) {
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='20' height='20'><circle cx='10' cy='10' r='6' fill='${color}' stroke='white' stroke-width='2'/></svg>`;
  return `url("data:image/svg+xml,${encodeURIComponent(svg)}") 10 10, auto`;
}

function emojiCursorSvg(emoji: string, size: number) {
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='${size}' height='${size}'><text x='50%' y='54%' font-size='${Math.round(size * 0.85)}' text-anchor='middle' dominant-baseline='middle'>${emoji}</text></svg>`;
  return `url("data:image/svg+xml,${encodeURIComponent(svg)}") ${Math.round(size / 2)} ${Math.round(size / 2)}, auto`;
}

// public/cursors/<theme>/cursor-32.png(32x32, 핫스팟 0,0)를 CSS cursor 이미지로 사용한다.
// CSS의 cursor: url(...)는 브라우저가 직접 렌더링하는 표준 기능이라 OS/플랫폼과 무관하게
// 동작한다 — Windows 전용 포맷인 .cur/.ani 원본은 쓰지 않고 PNG로 미리 변환해뒀기 때문에
// macOS Safari/Chrome에서도 동일하게 보인다.
function themeCursor(theme: string) {
  return `url('/cursors/${theme}/cursor-32.png') 0 0, auto`;
}

export const CURSOR_OPTIONS: CursorOption[] = [
  { id: 'off', label: '기본 커서 (끄기)', cssCursor: 'auto', trailGlyph: null, trailColor: '' },
  { id: 'dot', label: '파란 도트', cssCursor: dotCursorSvg('%233b82f6'), trailGlyph: '●', trailColor: '#3b82f6' },
  { id: 'sparkle', label: '반짝이', cssCursor: 'auto', trailGlyph: '✨', trailColor: '#f59e0b' },
  { id: 'paw', label: '고양이 발자국', cssCursor: 'auto', trailGlyph: '🐾', trailColor: '#a16207' },
  { id: 'heart', label: '하트', cssCursor: 'auto', trailGlyph: '💗', trailColor: '#ec4899' },
  { id: 'clover', label: '네잎클로버', cssCursor: 'auto', trailGlyph: '🍀', trailColor: '#16a34a' },
  { id: 'rainbow', label: '무지개', cssCursor: 'auto', trailGlyph: '🌈', trailColor: '#8b5cf6' },
  { id: 'pokemon', label: '포켓몬 (루카리오)', cssCursor: themeCursor('pokemon'), trailGlyph: null, trailColor: '' },
  { id: 'miku', label: '하츠네 미쿠', cssCursor: themeCursor('miku'), trailGlyph: null, trailColor: '' },
  { id: 'dove', label: '비둘기', cssCursor: themeCursor('dove'), trailGlyph: null, trailColor: '' },
  { id: 'hellokitty', label: '헬로키티', cssCursor: themeCursor('hellokitty'), trailGlyph: null, trailColor: '' },
  { id: 'pusheen', label: 'Pusheen 고양이', cssCursor: themeCursor('cat'), trailGlyph: null, trailColor: '' },
  {
    id: 'chaos',
    label: '🌀 카오스 (주의: 정신없음)',
    cssCursor: emojiCursorSvg('🌀', 44),
    trailGlyph: '💥',
    trailColor: '#ef4444',
    chaos: true,
  },
];

export function getCursorOption(id: string): CursorOption {
  return CURSOR_OPTIONS.find((option) => option.id === id) ?? CURSOR_OPTIONS[0];
}
