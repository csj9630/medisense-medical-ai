import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Sidebar, SidebarProvider } from '../Sidebar';
import { ThemeToggle } from '../Theme/ThemeToggle';
import { AdminNav } from '../Admin/AdminNav';
import { DocumentPreviewProvider, useDocumentPreview } from '../Chat/DocumentPreviewContext';
import { DocumentPreviewPanel } from '../Chat/DocumentPreviewPanel';

// 메인, 인증, 채팅, 마이페이지가 공유하는 단일 사이드바 레이아웃입니다.
//
// Sidebar / 본문(main) / 문서 미리보기 패널을 같은 레벨의 형제로 둔다.
// 패널을 main 안쪽에 중첩시키면 우측 상단 다크모드 토글처럼 top-right에
// 고정되는 다른 UI와 자리가 겹치기 때문에, 구조적으로 분리했다.
export function MainLayout() {
  return (
    <SidebarProvider>
      <DocumentPreviewProvider>
        <MainLayoutBody />
      </DocumentPreviewProvider>
    </SidebarProvider>
  );
}

function MainLayoutBody() {
  const { preview, setPreviewIndex, closePreview } = useDocumentPreview();
  const { pathname } = useLocation();
  // 관리자 페이지/대시보드는 채팅 기록·진료과 필터 등 상담용 사이드바가 의미가
  // 없어서, 로고만 있는 얇은 레일로 대신한다.
  const isAdminArea = pathname.startsWith('/admin') || pathname.startsWith('/dashboard');

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-white dark:bg-neutral-950">
      {isAdminArea ? <LogoOnlyRail /> : <Sidebar />}
      <main className="relative flex min-w-0 flex-1 flex-col">
        <div className="absolute right-4 top-4 z-10 flex items-center gap-2">
          <AdminNav />
          <ThemeToggle />
        </div>
        <Outlet />
      </main>
      {preview && (
        <DocumentPreviewPanel
          attachments={preview.attachments}
          index={preview.index}
          onIndexChange={setPreviewIndex}
          onClose={closePreview}
        />
      )}
    </div>
  );
}

function LogoOnlyRail() {
  const navigate = useNavigate();
  return (
    <aside className="flex h-full w-14 shrink-0 flex-col items-center border-r border-neutral-200 bg-neutral-50 py-3 dark:border-neutral-800 dark:bg-neutral-900">
      <button
        type="button"
        title="상담 화면으로 이동"
        aria-label="상담 화면으로 이동"
        onClick={() => navigate('/')}
        className="rounded-lg p-0.5 hover:bg-neutral-200 dark:hover:bg-neutral-800"
      >
        <img src="/logo-mark.png" alt="MediSense" className="h-5 w-5" />
      </button>
    </aside>
  );
}
