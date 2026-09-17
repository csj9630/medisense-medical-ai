import { useEffect, type ReactNode } from 'react';
import { X } from 'lucide-react';

type DocumentLightboxProps = {
  title: string;
  onClose: () => void;
  children: ReactNode;
};

// ImageLightbox와 같은 자리(전체화면 오버레이, Esc/배경 클릭/X로 닫기)를 쓰지만,
// PDF/Word처럼 뷰어 자체(브라우저 PDF 뷰어, 변환된 HTML)가 이미 스크롤/줌을
// 지원하는 콘텐츠엔 별도 확대·축소 버튼이 필요 없어서 그 부분만 뺐다.
export function DocumentLightbox({ title, onClose, children }: DocumentLightboxProps) {
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-black/70 p-4 sm:p-8" onClick={onClose}>
      <div
        className="flex h-full w-full flex-col overflow-hidden rounded-xl bg-white shadow-2xl dark:bg-neutral-900"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-neutral-200 px-4 py-2.5 dark:border-neutral-700">
          <p className="truncate text-sm font-medium text-neutral-700 dark:text-neutral-200">{title}</p>
          <button type="button" title="닫기 (Esc)" onClick={onClose} className="rounded-lg p-1.5 text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-800">
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-auto">{children}</div>
      </div>
    </div>
  );
}
