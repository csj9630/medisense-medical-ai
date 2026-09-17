import { createContext, useContext, useState, type ReactNode } from 'react';
import type { MessageAttachment } from '../../api/types';

type PreviewTarget = {
  attachments: MessageAttachment[];
  index: number;
};

type DocumentPreviewContextValue = {
  preview: PreviewTarget | null;
  /** attachments 전체 목록 + 클릭한 파일의 index를 넘긴다 — 여러 개면 패널에서 넘기며 볼 수 있다. */
  openPreview: (attachments: MessageAttachment[], index: number) => void;
  setPreviewIndex: (index: number) => void;
  closePreview: () => void;
};

const DocumentPreviewContext = createContext<DocumentPreviewContextValue | null>(null);

// 문서 미리보기 패널 상태를 레이아웃 레벨(MainLayout)에서 관리한다.
// 채팅 화면 내부의 상태로 두면 패널이 <main> 안에 중첩되어 우측 상단 다크모드
// 토글 같은 다른 top-right 고정 UI와 겹치는 문제가 생겨서, 사이드바/본문과
// 나란한 진짜 형제 레이아웃으로 분리했다.
export function DocumentPreviewProvider({ children }: { children: ReactNode }) {
  const [preview, setPreview] = useState<PreviewTarget | null>(null);

  return (
    <DocumentPreviewContext.Provider
      value={{
        preview,
        openPreview: (attachments, index) => setPreview({ attachments, index }),
        setPreviewIndex: (index) => setPreview((current) => (current ? { ...current, index } : current)),
        closePreview: () => setPreview(null),
      }}
    >
      {children}
    </DocumentPreviewContext.Provider>
  );
}

export function useDocumentPreview() {
  const context = useContext(DocumentPreviewContext);
  if (!context) throw new Error('useDocumentPreview는 DocumentPreviewProvider 안에서만 사용할 수 있습니다.');
  return context;
}
