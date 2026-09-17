import { FileDown, X } from 'lucide-react';
import type { Message } from '../../api/types';
import { formatMessageTime } from '../../utils/formatDate';
import {
  buildFilenameBase,
  buildTranscriptMarkdown,
  buildTranscriptText,
  downloadTextFile,
  openPrintableTranscript,
} from '../../utils/chatExport';

type Format = 'txt' | 'md' | 'pdf';

type ChatExportPreviewModalProps = {
  messages: Message[];
  title: string;
  onClose: () => void;
};

function roleLabel(role: Message['role']): string {
  return role === 'user' ? '환자' : 'AI 상담';
}

// "채팅내역 저장" 버튼을 누르면 바로 파일이 받아지는 대신, 실제로 어떤 내용이
// 저장되는지 먼저 미리 보여주고 그 안에서 형식을 고르게 한다 — 저장 전에 내용을
// 확인할 수 있어야 한다는 요청 반영.
export function ChatExportPreviewModal({ messages, title, onClose }: ChatExportPreviewModalProps) {
  function handleExport(format: Format) {
    const filenameBase = buildFilenameBase(messages);
    if (format === 'txt') {
      downloadTextFile(`${filenameBase}.txt`, buildTranscriptText(title, messages), 'text/plain');
    } else if (format === 'md') {
      downloadTextFile(`${filenameBase}.md`, buildTranscriptMarkdown(title, messages), 'text/markdown');
    } else {
      openPrintableTranscript(title, messages);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="채팅내역 미리보기"
    >
      <div
        className="flex max-h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-white shadow-xl dark:bg-neutral-900"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-neutral-200 px-5 py-3 dark:border-neutral-700">
          <h2 className="text-sm font-semibold text-neutral-800 dark:text-neutral-100">채팅내역 미리보기</h2>
          <button
            type="button"
            onClick={onClose}
            title="닫기"
            aria-label="닫기"
            className="rounded p-1 text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-800"
          >
            <X size={16} />
          </button>
        </div>

        <div className="thin-scrollbar flex-1 overflow-y-auto px-5 py-4">
          <p className="mb-1 text-xs text-neutral-400">전체 대화 원문입니다.</p>
          <h3 className="mb-3 text-base font-semibold text-neutral-900 dark:text-neutral-50">{title}</h3>
          <div className="flex flex-col gap-4">
            {messages.map((message) => (
              <div key={message.id}>
                <p className="mb-0.5 text-[11px] font-medium text-neutral-400">
                  {roleLabel(message.role)} · {formatMessageTime(message.createdAt)}
                </p>
                <p className="whitespace-pre-wrap break-words text-sm text-neutral-700 dark:text-neutral-200">
                  {message.content}
                </p>
                {message.attachments && message.attachments.length > 0 && (
                  <p className="mt-1 text-xs text-neutral-400">
                    첨부: {message.attachments.map((a) => a.name).join(', ')}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>

        <div className="border-t border-neutral-200 px-5 py-3 dark:border-neutral-700">
          <p className="mb-2 text-xs text-neutral-400">어떤 형식으로 저장할까요?</p>
          <div className="flex gap-2">
            {(['txt', 'md', 'pdf'] as Format[]).map((format) => (
              <button
                key={format}
                type="button"
                onClick={() => handleExport(format)}
                className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-neutral-200 py-2 text-xs font-medium uppercase text-neutral-600 hover:border-blue-400 hover:text-blue-600 dark:border-neutral-700 dark:text-neutral-300 dark:hover:border-blue-500 dark:hover:text-blue-400"
              >
                <FileDown size={13} />
                {format}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
