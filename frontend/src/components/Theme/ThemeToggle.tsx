import { Moon, Sun } from 'lucide-react';
import { useTheme } from './ThemeContext';

/** 우측 상단에 두는 라이트/다크 전환 스위치. */
export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const isDark = theme === 'dark';

  return (
    <button
      type="button"
      role="switch"
      aria-checked={isDark}
      title={isDark ? '라이트 모드로 전환' : '다크 모드로 전환'}
      onClick={toggle}
      className="relative inline-flex h-7 w-13 shrink-0 items-center rounded-full bg-neutral-200 transition-colors dark:bg-neutral-700"
      style={{ width: 52 }}
    >
      <span
        className={`flex h-5.5 w-5.5 items-center justify-center rounded-full bg-white text-neutral-500 shadow transition-transform dark:bg-neutral-900 dark:text-neutral-300 ${
          isDark ? 'translate-x-[27px]' : 'translate-x-1'
        }`}
        style={{ height: 22, width: 22 }}
      >
        {isDark ? <Moon size={13} /> : <Sun size={13} />}
      </span>
    </button>
  );
}
