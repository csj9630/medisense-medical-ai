import { useEffect, useRef, useState } from 'react';
import { useCursorFx } from './CursorFxContext';
import { CURSOR_OPTIONS, getCursorOption } from './cursorOptions';

type Particle = { id: number; x: number; y: number; glyph: string; color: string; big: boolean; rotation: number };

// chaos 옵션 전용 — 매 스폰마다 이 중 하나를 무작위로 뽑아 큰 사이즈/무지개색으로 뿌린다.
const CHAOS_GLYPHS = ['💥', '⚡', '🌈', '🔥', '✨', '🎉', '💫', '😵‍💫'];
const CHAOS_COLORS = ['#ef4444', '#f97316', '#eab308', '#22c55e', '#3b82f6', '#8b5cf6', '#ec4899'];

/** body에 커서 스타일 적용 + 마우스 이동 잔상 효과 + Alt+D 드롭다운 메뉴. */
export function CursorFxLayer() {
  const { enabled, cursorId, dropdownOpen, setCursorId, toggleEnabled, closeDropdown } = useCursorFx();
  const option = getCursorOption(cursorId);
  const [particles, setParticles] = useState<Particle[]>([]);
  const lastSpawnRef = useRef(0);
  const idRef = useRef(0);

  useEffect(() => {
    document.body.style.cursor = enabled ? option.cssCursor : '';
    return () => {
      document.body.style.cursor = '';
    };
  }, [enabled, option.cssCursor]);

  useEffect(() => {
    if (!enabled || !option.trailGlyph) return;

    function handleMouseMove(event: MouseEvent) {
      const now = performance.now();
      const throttleMs = option.chaos ? 16 : 45;
      if (now - lastSpawnRef.current < throttleMs) return;
      lastSpawnRef.current = now;

      // chaos는 한 번에 여러 개를 커서 주변에 흩뿌려서 "정신없음"을 낸다.
      const spawnCount = option.chaos ? 5 : 1;
      const spawned: Particle[] = [];
      for (let i = 0; i < spawnCount; i++) {
        const id = idRef.current++;
        spawned.push({
          id,
          x: event.clientX + (option.chaos ? (Math.random() - 0.5) * 70 : 0),
          y: event.clientY + (option.chaos ? (Math.random() - 0.5) * 70 : 0),
          glyph: option.chaos ? CHAOS_GLYPHS[Math.floor(Math.random() * CHAOS_GLYPHS.length)] : option.trailGlyph!,
          color: option.chaos ? CHAOS_COLORS[Math.floor(Math.random() * CHAOS_COLORS.length)] : option.trailColor,
          big: Boolean(option.chaos),
          rotation: option.chaos ? Math.random() * 360 - 180 : 0,
        });
      }

      setParticles((current) => [...current.slice(-(option.chaos ? 100 : 30)), ...spawned]);
      const lifespanMs = option.chaos ? 500 : 600;
      spawned.forEach((p) => {
        window.setTimeout(() => {
          setParticles((current) => current.filter((x) => x.id !== p.id));
        }, lifespanMs);
      });
    }

    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, [enabled, option.trailGlyph, option.chaos, option.trailColor]);

  return (
    <>
      {enabled &&
        option.trailGlyph &&
        particles.map((p) => (
          <span
            key={p.id}
            aria-hidden
            className={`pointer-events-none fixed z-[9999] select-none animate-[cursorfx-fade_0.6s_ease-out_forwards] ${
              p.big ? 'text-4xl' : 'text-sm'
            }`}
            style={{ left: p.x, top: p.y, color: p.color, transform: `rotate(${p.rotation}deg)` }}
          >
            {p.glyph}
          </span>
        ))}

      {dropdownOpen && (
        <div
          className="fixed right-4 top-4 z-[10000] w-56 rounded-xl border border-neutral-200 bg-white p-2 shadow-lg dark:border-neutral-700 dark:bg-neutral-800"
          role="menu"
        >
          <div className="flex items-center justify-between px-2 py-1">
            <p className="text-xs font-semibold text-neutral-500 dark:text-neutral-400">
              커서 디자인 (Alt+D)
            </p>
            <button
              type="button"
              title="닫기"
              onClick={closeDropdown}
              className="text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200"
            >
              ✕
            </button>
          </div>
          {CURSOR_OPTIONS.map((opt) => (
            <button
              key={opt.id}
              type="button"
              role="menuitemradio"
              aria-checked={cursorId === opt.id}
              onClick={() => setCursorId(opt.id)}
              className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm ${
                cursorId === opt.id
                  ? 'bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300'
                  : 'text-neutral-700 hover:bg-neutral-100 dark:text-neutral-200 dark:hover:bg-neutral-700'
              }`}
            >
              <span>{opt.trailGlyph ?? '⭘'}</span>
              {opt.label}
            </button>
          ))}
          <div className="mt-1 border-t border-neutral-100 px-2 pt-2 dark:border-neutral-700">
            <button
              type="button"
              onClick={toggleEnabled}
              className="w-full rounded-lg bg-neutral-900 py-1.5 text-xs font-medium text-white dark:bg-white dark:text-neutral-900"
            >
              {enabled ? 'OFF (Alt+S)' : 'ON (Alt+S)'}
            </button>
          </div>
        </div>
      )}
    </>
  );
}
