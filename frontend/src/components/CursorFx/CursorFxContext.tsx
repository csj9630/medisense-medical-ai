import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { CURSOR_OPTIONS } from './cursorOptions';

/**
 * 이스터에그: 커스텀 마우스 커서.
 * - Alt+D: 커서 디자인 선택 드롭다운 열기/닫기
 * - Alt+S: 현재 선택된 커서 ON/OFF
 * - 선택 상태는 localStorage에 TTL(24시간)과 함께 저장되어 새로고침/재접속에도 유지된다.
 *
 * ⚠️ 주의: Windows Chrome/Edge는 Alt+D가 브라우저 주소창 포커스 단축키로 예약되어 있어,
 * 페이지 JS가 keydown 이벤트 자체를 못 받는 경우가 있다. preventDefault로 최대한 막지만
 * 100% 보장은 안 되니, 안 먹히면 다른 조합(Alt+Shift+D 등)으로 바꾸는 걸 권장한다.
 */

const STORAGE_KEY = 'thegpt-cursorfx';
const TTL_MS = 24 * 60 * 60 * 1000; // 24시간

type StoredState = { enabled: boolean; cursorId: string; expiresAt: number };

function loadStoredState(): { enabled: boolean; cursorId: string } {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { enabled: false, cursorId: CURSOR_OPTIONS[1].id };
    const parsed = JSON.parse(raw) as StoredState;
    if (Date.now() > parsed.expiresAt) return { enabled: false, cursorId: parsed.cursorId };
    return { enabled: parsed.enabled, cursorId: parsed.cursorId };
  } catch {
    return { enabled: false, cursorId: CURSOR_OPTIONS[1].id };
  }
}

function persist(enabled: boolean, cursorId: string) {
  const state: StoredState = { enabled, cursorId, expiresAt: Date.now() + TTL_MS };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

type CursorFxContextValue = {
  enabled: boolean;
  cursorId: string;
  dropdownOpen: boolean;
  setCursorId: (id: string) => void;
  toggleEnabled: () => void;
  closeDropdown: () => void;
};

const CursorFxContext = createContext<CursorFxContextValue | null>(null);

export function CursorFxProvider({ children }: { children: ReactNode }) {
  const initial = loadStoredState();
  const [enabled, setEnabled] = useState(initial.enabled);
  const [cursorId, setCursorIdState] = useState(initial.cursorId);
  const [dropdownOpen, setDropdownOpen] = useState(false);

  function setCursorId(id: string) {
    setCursorIdState(id);
    persist(enabled, id);
  }

  function toggleEnabled() {
    setEnabled((current) => {
      const next = !current;
      persist(next, cursorId);
      return next;
    });
  }

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const altOnly = event.altKey && !event.ctrlKey && !event.metaKey && !event.shiftKey;
      if (!altOnly) return;

      // event.key가 아니라 event.code로 판정한다. macOS는 Option(=Alt)을 누른 채
      // D/S를 치면 event.key가 "d"/"s"가 아니라 "∂"/"ß" 같은 특수문자로 나온다
      // (Option이 죽은키/유니코드 입력을 겸하기 때문). event.code는 물리적 키 위치를
      // 그대로 보고하므로 Windows/Mac 어느 키보드/레이아웃에서도 동일하게 동작한다.
      if (event.code === 'KeyD') {
        event.preventDefault();
        setDropdownOpen((open) => !open);
      } else if (event.code === 'KeyS') {
        event.preventDefault();
        toggleEnabled();
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cursorId]);

  return (
    <CursorFxContext.Provider
      value={{
        enabled,
        cursorId,
        dropdownOpen,
        setCursorId,
        toggleEnabled,
        closeDropdown: () => setDropdownOpen(false),
      }}
    >
      {children}
    </CursorFxContext.Provider>
  );
}

export function useCursorFx() {
  const context = useContext(CursorFxContext);
  if (!context) throw new Error('useCursorFx는 CursorFxProvider 안에서만 사용할 수 있습니다.');
  return context;
}
