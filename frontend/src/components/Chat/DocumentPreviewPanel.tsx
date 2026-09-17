import { useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, FileText, Loader2, Maximize2, X } from 'lucide-react';
import { extractTextFromImage } from '../../api/documents';
import type { MessageAttachment } from '../../api/types';
import { maskPII } from '../../utils/piiMask';
import { DocumentLightbox } from './DocumentLightbox';
import { ImageLightbox } from './ImageLightbox';

type DocumentPreviewPanelProps = {
  attachments: MessageAttachment[];
  index: number;
  onIndexChange: (index: number) => void;
  onClose: () => void;
};

const WIDTH_STORAGE_KEY = 'thegpt_preview_panel_width';
const MIN_WIDTH = 300;
const MAX_WIDTH = 760;
const DEFAULT_WIDTH = 384;

// blob: URL 하나당 OCR을 한 번만 돌리면 되니, 패널을 닫았다 다시 열어도 재사용한다.
const ocrCache = new Map<string, string>();
// Word 문서도 마찬가지로 blob: URL 하나당 mammoth 변환을 한 번만 돌린다.
const wordHtmlCache = new Map<string, string>();

function isImage(attachment: MessageAttachment) {
  return attachment.type?.startsWith('image/') ?? /\.(png|jpe?g|gif|webp|bmp)$/i.test(attachment.name);
}

function isPdf(attachment: MessageAttachment) {
  return attachment.type === 'application/pdf' || /\.pdf$/i.test(attachment.name);
}

// mammoth는 OOXML(.docx)만 지원한다 - 구버전 바이너리 .doc은 다른 포맷이라 못 읽는다.
function isWord(attachment: MessageAttachment) {
  return (
    attachment.type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
    /\.docx$/i.test(attachment.name)
  );
}

// HWP는 한글과컴퓨터 전용 바이너리 포맷이라 브라우저에서 렌더링할 방법이 없다
// (쓸만한 JS 라이브러리 없음) - 이미지/PDF/Word처럼 확대해서 보여주는 대신
// "미리보기 미지원"임을 명확히 안내한다.
function isHwp(attachment: MessageAttachment) {
  return /\.hwpx?$/i.test(attachment.name);
}

// 원본 문서 vs 파싱된 텍스트를 나란히 보여주는 우측 패널.
// - 원본: 방금 이 세션에서 첨부한 파일(blob: URL 있음)만 실제로 보여줄 수 있다.
//   서버는 아직 첨부파일 메타데이터만 저장하고 실제 바이트는 저장하지 않아서
//   (Object Storage 연동 전), 새로고침/이전 대화에서 불러온 첨부는 안내만 표시한다.
// - 파싱된 텍스트: blob: URL이 있는 이미지 첨부는 /api/documents/ocr을 호출해 실제
//   추출 결과를 보여준다. 그 외(PDF, 저장 안 된 첨부)는 안내 문구만 표시.
// - 좌측 가장자리를 드래그해 폭을 조절할 수 있고(로컬에 기억), 첨부가 여러 개면
//   하단 썸네일 스트립 + 이전/다음 버튼으로 넘겨볼 수 있다.
export function DocumentPreviewPanel({ attachments, index, onIndexChange, onClose }: DocumentPreviewPanelProps) {
  const attachment = attachments[index];
  const [parsedText, setParsedText] = useState('');
  const [ocrLoading, setOcrLoading] = useState(false);
  const [ocrError, setOcrError] = useState<string | null>(null);
  const [width, setWidth] = useState(() => {
    const stored = Number(localStorage.getItem(WIDTH_STORAGE_KEY));
    return stored >= MIN_WIDTH && stored <= MAX_WIDTH ? stored : DEFAULT_WIDTH;
  });
  const resizingRef = useRef(false);

  useEffect(() => {
    if (!attachment) return;
    setOcrError(null);

    if (!attachment.url) {
      setOcrLoading(false);
      setParsedText(`"${attachment.name}"은 원본이 저장되지 않아 텍스트를 추출할 수 없어요 (스토리지 연동 전).`);
      return;
    }
    if (!isImage(attachment)) {
      setOcrLoading(false);
      setParsedText(`"${attachment.name}"은 아직 텍스트 추출을 지원하지 않는 형식이에요 (이미지만 지원).`);
      return;
    }

    const cached = ocrCache.get(attachment.url);
    if (cached !== undefined) {
      setOcrLoading(false);
      setParsedText(cached);
      return;
    }

    let cancelled = false;
    setOcrLoading(true);
    setParsedText('');

    (async () => {
      try {
        const blob = await fetch(attachment.url!).then((res) => res.blob());
        const file = new File([blob], attachment.name, { type: attachment.type });
        const result = await extractTextFromImage(file);
        // 처방전/검사결과지 등에 주민등록번호·전화번호·주소가 그대로 찍혀 나오는
        // 경우가 있어서, 화면에 보여주기 전에 마스킹한다 — 원문이 아니라 마스킹된
        // 텍스트를 캐싱/표시한다(캐시에도 원문 개인정보를 남기지 않기 위함).
        const text = result.text ? maskPII(result.text) : '(텍스트를 찾지 못했어요)';
        ocrCache.set(attachment.url!, text);
        if (!cancelled) setParsedText(text);
      } catch (error) {
        if (!cancelled) setOcrError(error instanceof Error ? error.message : '텍스트 추출에 실패했어요.');
      } finally {
        if (!cancelled) setOcrLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [attachment]);

  function startResize(event: React.MouseEvent) {
    event.preventDefault();
    resizingRef.current = true;
    document.body.style.cursor = 'col-resize';

    function handleMouseMove(moveEvent: MouseEvent) {
      if (!resizingRef.current) return;
      // 패널이 화면 우측에 붙어있으므로, 화면 오른쪽 끝에서 마우스 x좌표까지의 거리가 곧 폭.
      const next = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, window.innerWidth - moveEvent.clientX));
      setWidth(next);
    }
    function handleMouseUp() {
      resizingRef.current = false;
      document.body.style.cursor = '';
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      setWidth((current) => {
        localStorage.setItem(WIDTH_STORAGE_KEY, String(current));
        return current;
      });
    }
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  }

  if (!attachment) return null;

  return (
    <aside
      style={{ width }}
      className="relative flex h-full shrink-0 flex-col border-l border-neutral-200 bg-white dark:border-neutral-700 dark:bg-neutral-900"
    >
      {/* 리사이즈 핸들 */}
      <div
        onMouseDown={startResize}
        title="드래그해서 폭 조절"
        className="absolute -left-1 top-0 h-full w-2 cursor-col-resize select-none"
      />

      <div className="flex items-center justify-between border-b border-neutral-200 px-4 py-3 dark:border-neutral-700">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-neutral-800 dark:text-neutral-100">{attachment.name}</p>
          {attachments.length > 1 && (
            <p className="text-xs text-neutral-400">
              {index + 1} / {attachments.length}
            </p>
          )}
        </div>
        <button
          type="button"
          title="미리보기 닫기"
          onClick={onClose}
          className="rounded-lg p-1 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700 dark:hover:bg-neutral-800 dark:hover:text-neutral-200"
        >
          <X size={16} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        <p className="mb-1.5 text-xs font-semibold text-neutral-400">원본 문서</p>
        <OriginalPreview attachment={attachment} />

        <p className="mb-1.5 mt-4 text-xs font-semibold text-neutral-400">추출된 텍스트 (수정 가능)</p>
        {ocrLoading ? (
          <div className="flex items-center gap-2 rounded-lg border border-neutral-200 p-3 text-sm text-neutral-400 dark:border-neutral-700">
            <Loader2 size={14} className="animate-spin" />
            텍스트를 추출하고 있어요...
          </div>
        ) : ocrError ? (
          <p className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-600 dark:border-red-900 dark:bg-red-950 dark:text-red-400">
            {ocrError}
          </p>
        ) : (
          <textarea
            value={parsedText}
            onChange={(e) => setParsedText(e.target.value)}
            rows={10}
            className="w-full resize-none rounded-lg border border-neutral-200 p-2.5 text-sm text-neutral-800 focus:border-blue-400 focus:outline-none dark:border-neutral-700 dark:bg-neutral-800 dark:text-neutral-100"
          />
        )}
      </div>

      {attachments.length > 1 && (
        <div className="flex items-center gap-1.5 border-t border-neutral-200 px-2 py-2 dark:border-neutral-700">
          <button
            type="button"
            title="이전 파일"
            aria-label="이전 파일"
            disabled={index === 0}
            onClick={() => onIndexChange(index - 1)}
            className="shrink-0 rounded-lg p-1.5 text-neutral-400 hover:bg-neutral-100 disabled:opacity-30 disabled:hover:bg-transparent dark:hover:bg-neutral-800"
          >
            <ChevronLeft size={16} />
          </button>

          <div className="flex flex-1 gap-1.5 overflow-x-auto">
            {attachments.map((a, i) => (
              <button
                key={`${a.name}-${i}`}
                type="button"
                title={a.name}
                onClick={() => onIndexChange(i)}
                className={`flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-lg border text-neutral-400 ${
                  i === index
                    ? 'border-blue-500 ring-1 ring-blue-500'
                    : 'border-neutral-200 hover:border-neutral-300 dark:border-neutral-700'
                }`}
              >
                {isImage(a) && a.url ? (
                  <img src={a.url} alt={a.name} className="h-full w-full object-cover" />
                ) : (
                  <FileText size={16} />
                )}
              </button>
            ))}
          </div>

          <button
            type="button"
            title="다음 파일"
            aria-label="다음 파일"
            disabled={index === attachments.length - 1}
            onClick={() => onIndexChange(index + 1)}
            className="shrink-0 rounded-lg p-1.5 text-neutral-400 hover:bg-neutral-100 disabled:opacity-30 disabled:hover:bg-transparent dark:hover:bg-neutral-800"
          >
            <ChevronRight size={16} />
          </button>
        </div>
      )}
    </aside>
  );
}

function OriginalPreview({ attachment }: { attachment: MessageAttachment }) {
  const [lightboxOpen, setLightboxOpen] = useState(false);

  // 썸네일/다음·이전 이동으로 첨부가 바뀌면 이전 첨부 기준으로 열려있던 라이트박스는 닫는다.
  useEffect(() => {
    setLightboxOpen(false);
  }, [attachment.url]);

  if (!attachment.url) {
    return (
      <div className="flex h-40 flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-neutral-300 px-3 text-center text-xs text-neutral-400 dark:border-neutral-600">
        <FileText size={20} />
        <p>원본이 아직 서버에 저장되지 않았어요.</p>
        <p>(방금 첨부한 파일만 이 세션에서 미리볼 수 있어요 — 스토리지 연동 전)</p>
      </div>
    );
  }

  if (isImage(attachment)) {
    return (
      <>
        <button
          type="button"
          title="확대해서 보기"
          onClick={() => setLightboxOpen(true)}
          className="group relative block w-full overflow-hidden rounded-lg border border-neutral-200 dark:border-neutral-700"
        >
          <img src={attachment.url} alt={attachment.name} className="max-h-80 w-full object-contain" />
          <span className="absolute inset-0 flex items-center justify-center bg-black/0 opacity-0 transition-all group-hover:bg-black/30 group-hover:opacity-100">
            <Maximize2 size={20} className="text-white" />
          </span>
        </button>
        {lightboxOpen && (
          <ImageLightbox src={attachment.url} alt={attachment.name} onClose={() => setLightboxOpen(false)} />
        )}
      </>
    );
  }

  if (isPdf(attachment)) {
    return (
      <>
        <button
          type="button"
          title="확대해서 보기"
          onClick={() => setLightboxOpen(true)}
          className="group relative block w-full overflow-hidden rounded-lg border border-neutral-200 dark:border-neutral-700"
        >
          {/* 작은 패널 안에서는 마우스 조작(스크롤/드래그)이 브라우저 내장 PDF 뷰어에
              먹혀서 오히려 어색하므로, 여기선 순전히 미리보기용 - 실제 조작은
              확대 모달에서 하도록 클릭을 막는다(pointer-events-none). */}
          <iframe
            src={attachment.url}
            title={attachment.name}
            className="h-80 w-full pointer-events-none"
          />
          <span className="absolute inset-0 flex items-center justify-center bg-black/0 opacity-0 transition-all group-hover:bg-black/30 group-hover:opacity-100">
            <Maximize2 size={20} className="text-white" />
          </span>
        </button>
        {lightboxOpen && (
          <DocumentLightbox title={attachment.name} onClose={() => setLightboxOpen(false)}>
            <iframe src={attachment.url} title={attachment.name} className="h-full w-full" />
          </DocumentLightbox>
        )}
      </>
    );
  }

  if (isWord(attachment)) {
    return <WordPreview attachment={attachment} lightboxOpen={lightboxOpen} onOpenLightbox={() => setLightboxOpen(true)} onCloseLightbox={() => setLightboxOpen(false)} />;
  }

  if (isHwp(attachment)) {
    return (
      <div className="flex h-40 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-neutral-300 px-3 text-center text-xs text-neutral-400 dark:border-neutral-600">
        <FileText size={20} />
        <p>HWP는 미리보기를 지원하지 않는 형식이에요.</p>
        <a href={attachment.url} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline dark:text-blue-400">
          새 탭에서 열기
        </a>
      </div>
    );
  }

  return (
    <div className="flex h-40 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-neutral-300 text-xs text-neutral-400 dark:border-neutral-600">
      <FileText size={20} />
      <a href={attachment.url} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline dark:text-blue-400">
        새 탭에서 열기
      </a>
    </div>
  );
}

type WordPreviewProps = {
  attachment: MessageAttachment;
  lightboxOpen: boolean;
  onOpenLightbox: () => void;
  onCloseLightbox: () => void;
};

// .docx를 mammoth로 변환한 HTML을 보여준다 - 서식(글꼴 크기, 색 등)은 버리고
// 문단/제목/목록/표 등 구조만 살린 "단순화된" 렌더링이다(mammoth의 기본 동작 -
// 원본과 완전히 똑같이 보이진 않지만 내용 확인에는 충분하고, 별도 CSS 매핑
// 설정 없이도 안전하게 쓸 수 있다).
function WordPreview({ attachment, lightboxOpen, onOpenLightbox, onCloseLightbox }: WordPreviewProps) {
  const [html, setHtml] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    const cached = wordHtmlCache.get(attachment.url!);
    if (cached !== undefined) {
      setHtml(cached);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setHtml('');

    (async () => {
      try {
        // mammoth는 실제로 .docx를 열어볼 때만 쓰는 무거운 라이브러리라(변환 후
        // 번들 크기가 두 배 이상 뛴다), 정적 import 대신 필요한 시점에만 불러온다.
        const [{ default: mammoth }, buffer] = await Promise.all([
          import('mammoth'),
          fetch(attachment.url!).then((res) => res.arrayBuffer()),
        ]);
        const result = await mammoth.convertToHtml({ arrayBuffer: buffer });
        wordHtmlCache.set(attachment.url!, result.value);
        if (!cancelled) setHtml(result.value);
      } catch {
        if (!cancelled) setError('이 파일을 미리보기 형태로 변환하지 못했어요.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [attachment.url]);

  if (loading) {
    return (
      <div className="flex h-40 items-center justify-center gap-2 rounded-lg border border-neutral-200 text-sm text-neutral-400 dark:border-neutral-700">
        <Loader2 size={14} className="animate-spin" />
        문서를 불러오고 있어요...
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-40 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-neutral-300 px-3 text-center text-xs text-neutral-400 dark:border-neutral-600">
        <FileText size={20} />
        <p>{error}</p>
        <a href={attachment.url} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline dark:text-blue-400">
          새 탭에서 열기
        </a>
      </div>
    );
  }

  return (
    <>
      <button
        type="button"
        title="확대해서 보기"
        onClick={onOpenLightbox}
        className="group relative block max-h-80 w-full overflow-hidden rounded-lg border border-neutral-200 text-left dark:border-neutral-700"
      >
        <div
          className="word-preview-content pointer-events-none max-h-80 overflow-hidden p-3 text-sm text-neutral-800 dark:text-neutral-100"
          dangerouslySetInnerHTML={{ __html: html }}
        />
        <span className="absolute inset-0 flex items-center justify-center bg-black/0 opacity-0 transition-all group-hover:bg-black/30 group-hover:opacity-100">
          <Maximize2 size={20} className="text-white" />
        </span>
      </button>
      {lightboxOpen && (
        <DocumentLightbox title={attachment.name} onClose={onCloseLightbox}>
          <div
            className="word-preview-content mx-auto max-w-3xl p-8 text-neutral-800 dark:text-neutral-100"
            dangerouslySetInnerHTML={{ __html: html }}
          />
        </DocumentLightbox>
      )}
    </>
  );
}
