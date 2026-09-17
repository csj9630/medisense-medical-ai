export const OCR_CHUNK_SIZE_OPTIONS = [
  50,
  100,
  200,
  256,
  300,
  400,
  500,
  512,
  600,
  700,
  800,
  900,
  1000,
  1024,
  1100,
  1200,
  1300,
  1400,
  1500,
  1600,
  1700,
  1800,
  1900,
  2000,
  2048,
] as const;
export type OcrChunkSize = (typeof OCR_CHUNK_SIZE_OPTIONS)[number];

export const OCR_OVERLAP_PERCENT_OPTIONS = [0, 10, 15, 20] as const;
export type OcrOverlapPercent = (typeof OCR_OVERLAP_PERCENT_OPTIONS)[number];

const LEGACY_OVERLAP_PRESETS: Partial<
  Record<OcrChunkSize, Record<OcrOverlapPercent, number>>
> = {
  256: { 0: 0, 10: 25, 15: 40, 20: 50 },
  512: { 0: 0, 10: 50, 15: 75, 20: 100 },
  1024: { 0: 0, 10: 100, 15: 150, 20: 200 },
  2048: { 0: 0, 10: 200, 15: 300, 20: 400 },
};

export const OCR_CHUNK_SIZE: OcrChunkSize = 512;
export const OCR_OVERLAP_PERCENT: OcrOverlapPercent = 10;

export function getOcrOverlap(
  chunkSize: OcrChunkSize,
  percentage: OcrOverlapPercent,
) {
  const legacyPreset = LEGACY_OVERLAP_PRESETS[chunkSize];
  if (legacyPreset) return legacyPreset[percentage];
  if (percentage === 0) return 0;

  // 새 50·100자 단위 옵션은 선택한 비율을 5자 단위로 반올림한다.
  return Math.max(5, Math.round((chunkSize * percentage) / 100 / 5) * 5);
}

export const OCR_OVERLAP = getOcrOverlap(
  OCR_CHUNK_SIZE,
  OCR_OVERLAP_PERCENT,
);
export const OCR_ACCEPT = ".pdf,.png,.jpg,.jpeg,.docx,.pptx,.json,.jsonl,.csv,.txt,.zip";
export const OCR_MAX_FILE_BYTES = 8 * 1024 * 1024 * 1024;
export const OCR_INLINE_FILE_BYTES = 20 * 1024 * 1024;
export const OCR_LARGE_FILE_EXTENSIONS = new Set(["json", "jsonl", "csv", "txt", "zip"]);
export const OCR_SUPPORTED_EXTENSIONS = new Set([
  "pdf",
  "png",
  "jpg",
  "jpeg",
  "docx",
  "pptx",
  "json",
  "jsonl",
  "csv",
  "txt",
  "zip",
]);
