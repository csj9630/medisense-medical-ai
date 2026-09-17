type AnalyzeOptions = {
  chunkSize: number;
  overlap: number;
  signal?: AbortSignal;
};
export type AnalyzeDocumentRequest = AnalyzeOptions & (
  | { sourceType: 'file'; file: File }
  | { sourceType: 'url'; url: string }
);
export type SaveDocumentRequest = { jobId: string };
export type SaveDocumentResult = {
  message: string;
  documentId: string;
  chunkCount: number;
  embeddingProvider: string;
  embeddingDimension: number;
  embeddingModel: string;
};

export type OcrProgressUpdate = {
  stage: string;
  progress: number;
  message: string;
};

export type OcrJobCreated = {
  jobId: string;
  status: 'queued';
};

export type OcrMultipartUploadSession = {
  uploadId: string;
  objectKey: string;
  partSize: number;
  partCount: number;
};

export type OcrMultipartCompletedPart = {
  partNumber: number;
  etag: string;
};

export type OcrJobStatus = OcrProgressUpdate & {
  jobId: string;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  result: OcrDocumentPayload | null;
  error: string | null;
};

export type OcrProgressListener = (progress: OcrProgressUpdate) => void;

export type OcrDocumentPayload = {
  documentName: string;
  pageCount: number | null;
  characterCount: number;
  estimatedChunks: number;
  confidence: number;
  extractedText: string;
  chunks: string[];
  readiness: 'review' | 'ready';
  notes: string[];
  sourceType: 'file' | 'url';
  sourceUrl: string | null;
};

export type OcrDocumentResult = OcrDocumentPayload & { jobId: string };
