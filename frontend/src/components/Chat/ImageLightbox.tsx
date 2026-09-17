import { useEffect, useState } from 'react';
import { Minus, Plus, RotateCcw, X } from 'lucide-react';

type ImageLightboxProps = {
  src: string;
  alt: string;
  onClose: () => void;
};

const MIN_ZOOM = 0.5;
const MAX_ZOOM = 4;
const ZOOM_STEP = 0.25;

// 원본 이미지를 전체화면으로 확대해서 보는 라이트박스.
// 버튼/휠로 배율 조절, 배율이 크면 스크롤로 이동. Esc·배경 클릭·X로 닫는다.
export function ImageLightbox({ src, alt, onClose }: ImageLightboxProps) {
  const [zoom, setZoom] = useState(1);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  function handleWheel(event: React.WheelEvent) {
    event.preventDefault();
    setZoom((z) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z - event.deltaY * 0.001)));
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-black/90" onClick={onClose}>
      <div className="flex items-center justify-between gap-2 p-3" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-1 rounded-lg bg-white/10 p-1">
          <button
            type="button"
            title="축소"
            onClick={() => setZoom((z) => Math.max(MIN_ZOOM, +(z - ZOOM_STEP).toFixed(2)))}
            className="rounded p-1.5 text-white hover:bg-white/20"
          >
            <Minus size={16} />
          </button>
          <span className="w-12 text-center text-xs tabular-nums text-white">{Math.round(zoom * 100)}%</span>
          <button
            type="button"
            title="확대"
            onClick={() => setZoom((z) => Math.min(MAX_ZOOM, +(z + ZOOM_STEP).toFixed(2)))}
            className="rounded p-1.5 text-white hover:bg-white/20"
          >
            <Plus size={16} />
          </button>
          <button type="button" title="원래 크기" onClick={() => setZoom(1)} className="rounded p-1.5 text-white hover:bg-white/20">
            <RotateCcw size={14} />
          </button>
        </div>
        <button type="button" title="닫기 (Esc)" onClick={onClose} className="rounded-lg p-1.5 text-white hover:bg-white/20">
          <X size={20} />
        </button>
      </div>

      <div className="flex-1 overflow-auto" onWheel={handleWheel} onClick={(e) => e.stopPropagation()}>
        <div className="flex min-h-full w-full items-center justify-center p-6">
          <img
            src={src}
            alt={alt}
            style={{ transform: `scale(${zoom})` }}
            className="max-w-none select-none transition-transform"
            draggable={false}
          />
        </div>
      </div>
    </div>
  );
}
