import { FileText, Trash2 } from "lucide-react";
import type { AsyncStatus } from "../../types/common";
import type { OcrProgressUpdate } from "../../types/ocr";

const formatBytes = (bytes: number) =>
  bytes < 1024
    ? `${bytes} B`
    : bytes < 1024 * 1024
      ? `${(bytes / 1024).toFixed(1)} KB`
      : bytes < 1024 * 1024 * 1024
        ? `${(bytes / 1024 / 1024).toFixed(1)} MB`
        : `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;

export function SelectedFile({
  file,
  selected,
  status,
  progress,
  disabled,
  onSelect,
  onRemove,
}: {
  file: File;
  selected: boolean;
  status: AsyncStatus;
  progress: OcrProgressUpdate;
  disabled: boolean;
  onSelect: () => void;
  onRemove: () => void;
}) {
  const statusLabel = status === "loading"
    ? `${progress.progress}%`
    : status === "success"
      ? "완료"
      : status === "error"
        ? "실패"
        : "대기";
  return (
    <div className={`selected-file ${selected ? "is-selected" : ""}`} aria-live="polite">
      <button type="button" className="selected-file-main" onClick={onSelect}>
        <span className="file-icon">
          <FileText size={19} />
        </span>
        <span className="selected-file-info">
          <strong>{file.name}</strong>
          <span>{formatBytes(file.size)} · {file.type || "형식 정보 없음"}</span>
        </span>
        <span className={`selected-file-status ${status}`}>{statusLabel}</span>
      </button>
      <button
        type="button"
        className="icon-button"
        disabled={disabled}
        onClick={onRemove}
        aria-label={`${file.name} 제거`}
      >
        <Trash2 size={17} />
      </button>
    </div>
  );
}
