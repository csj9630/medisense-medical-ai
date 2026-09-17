import type { OcrDocumentResult } from "../types/ocr";

export function createOcrMockResult(
  documentName: string,
  isPdf: boolean,
): OcrDocumentResult {
  const extension = documentName.split(".").pop()?.toLowerCase();
  return {
    sourceType: "file",
    sourceUrl: null,
    jobId: "mock-ocr-job",
    documentName,
    pageCount: extension === "docx" ? null : isPdf ? 4 : 1,
    characterCount: isPdf ? 4_286 : 1_248,
    estimatedChunks: isPdf ? 11 : 4,
    confidence: isPdf ? 94.8 : 97.2,
    extractedText:
      "(front)환자의 현재 증상과 과거 병력을 함께 검토해야 합니다. 문서에 포함된 검사 결과는 임상적 판단을 보조하기 위한 참고 자료이며, 최종 진단은 의료 전문가의 확인이 필요합니다. 복용 중인 약물과 알레르기 정보를 먼저 확인하고 필요한 추가 검사를 결정합니다.",
    chunks: [
      "(front)[Chunk 01] 환자의 현재 증상과 과거 병력을 함께 검토해야 합니다. 문서에 포함된 검사 결과는 임상적 판단을 보조하기 위한 참고 자료입니다.",
      "(front)[Chunk 02] 최종 진단은 의료 전문가의 확인이 필요합니다. 복용 중인 약물과 알레르기 정보를 먼저 확인하고 필요한 추가 검사를 결정합니다.",
    ],
    readiness: isPdf ? "review" : "ready",
    notes: isPdf
      ? [
          "(front)",
          "표가 포함된 페이지는 열 순서를 확인해 주세요.",
          "개인정보가 포함되었는지 등록 전에 검토해 주세요.",
        ]
      : [
          "(front)",
          "이미지 대비가 양호합니다.",
          "등록 전 추출 문장의 오탈자를 확인해 주세요.",
        ],
  };
}
