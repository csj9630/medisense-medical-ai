import {
  OCR_CHUNK_SIZE_OPTIONS,
  OCR_OVERLAP_PERCENT_OPTIONS,
  type OcrChunkSize,
  type OcrOverlapPercent,
} from "../../constants/adminOptions";

const CHUNK_LABELS: Partial<Record<OcrChunkSize, string>> = {
  50: "50자 · 최소",
  100: "100자 · 짧은 문맥",
  256: "256자 · 세밀",
  512: "512자 · 기본",
  1024: "1,024자 · 긴 문맥",
  2048: "2,048자 · 매우 긴 문맥",
};

function chunkLabel(value: OcrChunkSize) {
  return CHUNK_LABELS[value] ?? `${value.toLocaleString()}자`;
}

const OVERLAP_LABELS: Record<OcrOverlapPercent, string> = {
  0: "없음",
  10: "약 10% · 기본",
  15: "약 15%",
  20: "약 20%",
};

export function OcrChunkSettings({
  chunkSize,
  overlap,
  overlapPercent,
  disabled,
  onChunkSizeChange,
  onOverlapPercentChange,
}: {
  chunkSize: OcrChunkSize;
  overlap: number;
  overlapPercent: OcrOverlapPercent;
  disabled: boolean;
  onChunkSizeChange: (value: OcrChunkSize) => void;
  onOverlapPercentChange: (value: OcrOverlapPercent) => void;
}) {
  return (
    <section className="ocr-chunk-settings" aria-labelledby="ocr-chunk-title">
      <div className="ocr-chunk-heading">
        <strong id="ocr-chunk-title">RAG Chunk 설정</strong>
        <span>OCR 추출 후 텍스트 분할에 적용됩니다.</span>
      </div>
      <div className="ocr-chunk-options">
        <label className="admin-field">
          <span>Chunk Size</span>
          <select
            value={chunkSize}
            disabled={disabled}
            onChange={(event) =>
              onChunkSizeChange(Number(event.target.value) as OcrChunkSize)
            }
          >
            {OCR_CHUNK_SIZE_OPTIONS.map((value) => (
              <option key={value} value={value}>
                {chunkLabel(value)}
              </option>
            ))}
          </select>
        </label>
        <label className="admin-field">
          <span>Overlap</span>
          <select
            value={overlapPercent}
            disabled={disabled}
            onChange={(event) =>
              onOverlapPercentChange(
                Number(event.target.value) as OcrOverlapPercent,
              )
            }
          >
            {OCR_OVERLAP_PERCENT_OPTIONS.map((value) => (
              <option key={value} value={value}>
                {OVERLAP_LABELS[value]}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="ocr-chunk-summary">
        서버 전송값: Chunk {chunkSize.toLocaleString()}자 · Overlap{" "}
        {overlap.toLocaleString()}자
      </p>
    </section>
  );
}
