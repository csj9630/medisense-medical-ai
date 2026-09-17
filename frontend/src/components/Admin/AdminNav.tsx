import { useState } from 'react';
import { BarChart3, LayoutDashboard, Settings } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../../features/auth/AuthContext';

const DESTINATIONS = [
  { to: '/admin', label: '관리자페이지', icon: Settings },
  { to: '/dashboard', label: '대시보드', icon: BarChart3 },
] as const;

/** 라이트/다크모드 토글 옆에 두는 관리자 전용 이동 버튼. 관리자페이지/대시보드
 * 두 곳 중 고를 수 있는 드롭다운이다(ModelSelect.tsx와 같은 패턴).
 * 관리자(is_admin) 계정이 아니면 버튼 자체를 렌더링하지 않는다. */
export function AdminNav() {
  const { user } = useAuth();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const isAdmin = Boolean(user?.is_admin);

  if (!isAdmin) {
    return null;
  }

  return (
    <div className="relative">
      <button
        type="button"
        title="관리자 메뉴"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-neutral-500 transition-colors hover:bg-neutral-200 hover:text-neutral-900 dark:text-neutral-300 dark:hover:bg-neutral-700 dark:hover:text-white"
      >
        <LayoutDashboard size={16} />
      </button>

      {open && (
        <>
          {/* 바깥 클릭 시 닫기용 오버레이 */}
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full z-20 mt-1.5 w-44 rounded-xl border border-neutral-200 bg-white p-1.5 shadow-lg dark:border-neutral-700 dark:bg-neutral-800">
            {DESTINATIONS.map(({ to, label, icon: Icon }) => {
              const active = location.pathname === to;
              return (
                <Link
                  key={to}
                  to={to}
                  onClick={() => setOpen(false)}
                  className={`flex items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm ${
                    active
                      ? 'bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300'
                      : 'text-neutral-700 hover:bg-neutral-100 dark:text-neutral-200 dark:hover:bg-neutral-700'
                  }`}
                >
                  <Icon size={14} />
                  {label}
                </Link>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
