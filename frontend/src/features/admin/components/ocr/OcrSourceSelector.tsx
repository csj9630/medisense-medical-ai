import { Globe2, Upload } from "lucide-react";

export function OcrSourceSelector({
  value,
  disabled,
  onChange,
}: {
  value: "file" | "url";
  disabled: boolean;
  onChange: (value: "file" | "url") => void;
}) {
  return (
    <div
      className="ocr-source-selector"
      role="group"
      aria-label="OCR 입력 방식"
    >
      <button
        type="button"
        className={value === "file" ? "active" : ""}
        aria-pressed={value === "file"}
        disabled={disabled}
        onClick={() => onChange("file")}
      >
        <Upload size={15} /> 문서 파일
      </button>
      <button
        type="button"
        className={value === "url" ? "active" : ""}
        aria-pressed={value === "url"}
        disabled={disabled}
        onClick={() => onChange("url")}
      >
        <Globe2 size={15} /> 웹페이지 URL
      </button>
    </div>
  );
}
