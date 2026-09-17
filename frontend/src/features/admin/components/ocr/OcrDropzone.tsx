import { useRef, useState, type DragEvent } from "react";
import { UploadCloud } from "lucide-react";
import { OCR_ACCEPT } from "../../constants/adminOptions";

export function OcrDropzone({
  disabled,
  onSelect,
}: {
  disabled: boolean;
  onSelect: (files: File[]) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  function drop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    const files = Array.from(event.dataTransfer.files);
    if (files.length) onSelect(files);
  }
  return (
    <div
      className={`file-dropzone ${dragging ? "is-dragging" : ""}`}
      onDragEnter={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={() => setDragging(false)}
      onDrop={drop}
    >
      <UploadCloud aria-hidden="true" size={32} />
      <strong>문서를 여러 개 끌어 놓거나 직접 선택하세요</strong>
      <span>PDF, PNG, JPG, DOCX, PPTX, JSON, JSONL, CSV, TXT, ZIP · 파일당 8GB 이하 · 최대 5개</span>
      <button
        className="admin-secondary-button"
        type="button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
      >
        파일 선택
      </button>
      <input
        ref={inputRef}
        className="admin-visually-hidden"
        type="file"
        multiple
        accept={OCR_ACCEPT}
        aria-label="OCR 테스트 파일 선택"
        disabled={disabled}
        onChange={(event) => {
          const files = Array.from(event.target.files ?? []);
          if (files.length) onSelect(files);
          event.target.value = "";
        }}
      />
    </div>
  );
}
