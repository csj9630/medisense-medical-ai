import { useLayoutEffect, useRef, useState, type FormEvent } from 'react';
import { Loader2, Plus, Send, X } from 'lucide-react';
import { ModelSelect } from './ModelSelect';
import {
  describeFileMerge,
  mergeSelectedFiles,
  MESSAGE_UPLOAD_ACCEPT,
  MESSAGE_UPLOAD_EXTENSIONS,
} from '../../utils/uploadFiles';

// 일반 이미지가 의료 영상인지 확장자만으로 판별할 수 없으므로 업로드는 허용하되
// 현재 분석 범위를 안내한다. DICOM은 공통 허용 확장자에 없으므로 선택 단계에서 제외된다.
const IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg'];

function getExtension(file: File) {
  return file.name.split('.').pop()?.toLowerCase() ?? '';
}

function isImageFile(file: File) {
  return IMAGE_EXTENSIONS.includes(getExtension(file)) || file.type.startsWith('image/');
}

type MessageInputProps = {
  onSend: (content: string, files: File[]) => void;
  disabled?: boolean;
  placeholder?: string;
};

// 줄바꿈 없이 긴 텍스트를 쳐도(가로로만 길어짐) 한 줄 높이에 그대로 갇혀서 textarea
// 자체 스크롤이 생기는 문제가 있었다 — rows={1}만으로는 내용에 따라 높이가 안
// 늘어난다. 입력할 때마다 실제 콘텐츠 높이(scrollHeight)에 맞춰 직접 높이를
// 갱신해야 진짜 "자라는 입력창"이 된다. MAX_TEXTAREA_HEIGHT_PX에 도달하면 CSS
// max-height가 더 이상 못 늘어나게 막고, 그 다음부터는 textarea 내부 스크롤로 넘어간다.
const MAX_TEXTAREA_HEIGHT_PX = 160;

export function MessageInput({ onSend, disabled, placeholder = '메시지를 입력하세요' }: MessageInputProps) {
  const [text, setText] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [imageWarning, setImageWarning] = useState(false);
  const [fileError, setFileError] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, MAX_TEXTAREA_HEIGHT_PX)}px`;
  }, [text]);

  function handleFilesSelected(selected: FileList | null) {
    if (!selected || selected.length === 0) return;

    const merged = mergeSelectedFiles(
      files,
      Array.from(selected),
      MESSAGE_UPLOAD_EXTENSIONS,
    );
    setFiles(merged.files);
    setImageWarning(merged.files.some(isImageFile));
    setFileError(describeFileMerge(merged, 'PDF, PNG, JPG, DOCX, PPTX, TXT, CSV'));
    if (fileInputRef.current) fileInputRef.current.value = '';
  }

  function removeFile(index: number) {
    setFiles((current) => {
      const next = current.filter((_, i) => i !== index);
      setImageWarning(next.some(isImageFile));
      return next;
    });
    setFileError('');
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = text.trim();
    if (!trimmed && files.length === 0) return;
    if (disabled) return;

    onSend(trimmed, files);
    setText('');
    setFiles([]);
    setImageWarning(false);
    setFileError('');
  }

  return (
    <form onSubmit={handleSubmit} className="w-full">
      {imageWarning && (
        <div className="mb-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300">
          이미지는 첨부되지만, MRI·CT·X-Ray 등 의료 영상은 아직 분석할 수 없어 해당 부분은 제외하고
          답변이 생성돼요. 증상은 최대한 글로 함께 적어주시면 더 정확한 답변을 드릴 수 있어요.
        </div>
      )}

      {fileError && (
        <div className="mb-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300" role="alert">
          {fileError}
        </div>
      )}

      {files.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {files.map((file, index) => (
            <span
              key={`${file.name}-${index}`}
              className="flex items-center gap-1 rounded-full bg-neutral-100 px-2.5 py-1 text-xs text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300"
            >
              {file.name}
              <button
                type="button"
                title={`${file.name} 첨부 취소`}
                aria-label={`${file.name} 첨부 취소`}
                onClick={() => removeFile(index)}
                className="text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200"
              >
                <X size={12} />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Claude 검색창 참고 레이아웃: 위쪽은 텍스트 입력 전용 줄, 아래쪽이 도구 모음 줄 */}
      <div className="flex flex-col gap-2.5 rounded-3xl border border-neutral-200 bg-white px-4 py-3 shadow-sm dark:border-neutral-700 dark:bg-neutral-900">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSubmit(e);
            }
          }}
          placeholder={disabled ? '전송 중이에요...' : placeholder}
          rows={1}
          style={{ maxHeight: MAX_TEXTAREA_HEIGHT_PX }}
          className="thin-scrollbar w-full resize-none overflow-y-auto bg-transparent text-sm text-neutral-800 placeholder:text-neutral-400 focus:outline-none dark:text-neutral-100 dark:placeholder:text-neutral-500"
        />

        <div className="flex items-center justify-between">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={MESSAGE_UPLOAD_ACCEPT}
            disabled={disabled}
            className="hidden"
            onChange={(e) => handleFilesSelected(e.target.files)}
          />
          <button
            type="button"
            title="파일 첨부"
            aria-label="파일 첨부"
            disabled={disabled}
            onClick={() => fileInputRef.current?.click()}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-neutral-400 hover:bg-neutral-100 hover:text-neutral-600 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-white/10 dark:hover:text-neutral-200"
          >
            <Plus size={18} />
          </button>

          <div className="flex items-center gap-1">
            <ModelSelect />
            <button
              type="submit"
              disabled={disabled || (!text.trim() && files.length === 0)}
              title="메시지 보내기"
              aria-label="메시지 보내기"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-600 text-white disabled:bg-neutral-200 disabled:text-neutral-400 dark:disabled:bg-neutral-800 dark:disabled:text-neutral-600"
            >
              {disabled ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
            </button>
          </div>
        </div>
      </div>

      {/* 답변 말풍선 위 안내 배너와 별개로, 입력창 바로 아래에도 항상 보이는 짧은 문구를
          둔다 — 배너는 답변이 온 뒤에만 보이니, 메시지를 보내기 전부터 계속 보이는
          자리도 필요하다는 피드백 반영. */}
      <p className="mt-2 text-center text-[11px] text-neutral-400 dark:text-neutral-500">
        MediSense는 실수를 할 수 있어요. 답변은 참고용이며, 진단은 반드시 전문가와 상담하세요.
      </p>
    </form>
  );
}
