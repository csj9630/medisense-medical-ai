import { useState } from 'react';
import { Download } from 'lucide-react';
import type { Message } from '../../api/types';
import { ChatExportPreviewModal } from './ChatExportPreviewModal';

type ChatExportMenuProps = {
  messages: Message[];
  title: string;
};

// 버튼을 누르면 바로 파일 형식을 고르게 하지 않고, 먼저 미리보기 모달을 띄운다 —
// 저장하기 전에 실제로 뭐가 저장되는지 확인할 수 있게 하기 위함. 형식 선택은
// 모달 안(ChatExportPreviewModal)에서 이뤄진다.
export function ChatExportMenu({ messages, title }: ChatExportMenuProps) {
  const [previewOpen, setPreviewOpen] = useState(false);

  function openPreview() {
    if (messages.length === 0) {
      window.alert('저장할 대화 내용이 없어요.');
      return;
    }
    setPreviewOpen(true);
  }

  return (
    <>
      <button
        type="button"
        title="채팅내역 저장"
        onClick={openPreview}
        className="flex items-center gap-1.5 rounded-lg border border-neutral-200 px-2.5 py-1.5 text-xs font-medium text-neutral-600 hover:bg-neutral-100 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
      >
        <Download size={14} />
        채팅내역 저장
      </button>

      {previewOpen && (
        <ChatExportPreviewModal messages={messages} title={title} onClose={() => setPreviewOpen(false)} />
      )}
    </>
  );
}
