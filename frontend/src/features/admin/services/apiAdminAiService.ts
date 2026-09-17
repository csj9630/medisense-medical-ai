import { apiClient } from '../../../services/apiClient';
import { authStorage } from '../../auth/authStorage';
import {
  OCR_INLINE_FILE_BYTES,
  OCR_LARGE_FILE_EXTENSIONS,
} from '../constants/adminOptions';
import type { LlmModelDefinition, LlmModelResult, RunLlmModelRequest } from '../types/llm';
import type {
  AnalyzeDocumentRequest,
  OcrDocumentResult,
  OcrJobCreated,
  OcrJobStatus,
  OcrMultipartCompletedPart,
  OcrMultipartUploadSession,
  OcrProgressListener,
  SaveDocumentRequest,
  SaveDocumentResult,
} from '../types/ocr';
import type { AdminAiService } from './adminAiService';

const OCR_JOB_POLL_INTERVAL_MS = 700;
const MULTIPART_UPLOAD_CONCURRENCY = 3;

function waitForNextPoll(signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('OCR 상태 조회가 취소되었습니다.', 'AbortError'));
      return;
    }

    const timer = window.setTimeout(() => {
      signal?.removeEventListener('abort', handleAbort);
      resolve();
    }, OCR_JOB_POLL_INTERVAL_MS);
    const handleAbort = () => {
      window.clearTimeout(timer);
      reject(new DOMException('OCR 상태 조회가 취소되었습니다.', 'AbortError'));
    };
    signal?.addEventListener('abort', handleAbort, { once: true });
  });
}

function fileExtension(file: File) {
  return file.name.split('.').pop()?.toLowerCase() ?? '';
}

async function pollJob(
  job: OcrJobCreated,
  signal: AbortSignal | undefined,
  onProgress: OcrProgressListener | undefined,
  progressStart = 0,
  progressSpan = 100,
): Promise<OcrDocumentResult> {
  while (true) {
    const status = await apiClient<OcrJobStatus>(
      `/admin/ocr/jobs/${encodeURIComponent(job.jobId)}`,
      { signal, token: authStorage.getToken() },
    );
    onProgress?.({
      stage: status.stage,
      progress: Math.min(100, Math.round(progressStart + (status.progress * progressSpan) / 100)),
      message: status.message,
    });

    if (status.status === 'completed') {
      if (!status.result) throw new Error('완료된 OCR 작업에 분석 결과가 없습니다.');
      return { ...status.result, jobId: status.jobId };
    }
    if (status.status === 'failed') {
      throw new Error(status.error ?? 'OCR 문서 분석에 실패했습니다.');
    }
    await waitForNextPoll(signal);
  }
}

async function uploadLargeDocument(
  request: Extract<AnalyzeDocumentRequest, { sourceType: 'file' }>,
  onProgress?: OcrProgressListener,
): Promise<OcrJobCreated> {
  if (!OCR_LARGE_FILE_EXTENSIONS.has(fileExtension(request.file))) {
    throw new Error('20MB 초과 파일은 JSON, JSONL, CSV, TXT 또는 ZIP 형식만 분석할 수 있습니다.');
  }

  const token = authStorage.getToken();
  let session: OcrMultipartUploadSession | null = null;
  let uploadCompleted = false;
  try {
    session = await apiClient<OcrMultipartUploadSession>('/admin/ocr/uploads/init', {
      method: 'POST',
      token,
      signal: request.signal,
      body: JSON.stringify({
        fileName: request.file.name,
        fileSize: request.file.size,
        contentType: request.file.type || 'application/octet-stream',
      }),
    });

    const parts: OcrMultipartCompletedPart[] = [];
    let nextPartNumber = 1;
    let uploadedBytes = 0;
    const worker = async () => {
      while (nextPartNumber <= session!.partCount) {
        const partNumber = nextPartNumber++;
        const start = (partNumber - 1) * session!.partSize;
        const end = Math.min(start + session!.partSize, request.file.size);
        const partUrl = await apiClient<{ uploadUrl: string }>('/admin/ocr/uploads/part-url', {
          method: 'POST',
          token,
          signal: request.signal,
          body: JSON.stringify({
            uploadId: session!.uploadId,
            objectKey: session!.objectKey,
            partNumber,
          }),
        });
        const response = await fetch(partUrl.uploadUrl, {
          method: 'PUT',
          body: request.file.slice(start, end),
          signal: request.signal,
        });
        if (!response.ok) {
          throw new Error(`파일 Part ${partNumber} 업로드에 실패했습니다. (${response.status})`);
        }
        const etag = response.headers.get('ETag');
        if (!etag) {
          throw new Error('R2 CORS 설정에서 ETag 응답 헤더를 노출해야 합니다.');
        }
        parts.push({ partNumber, etag });
        uploadedBytes += end - start;
        onProgress?.({
          stage: 'uploading',
          progress: Math.max(1, Math.round((uploadedBytes / request.file.size) * 55)),
          message: `R2에 분할 업로드 중입니다. (${parts.length}/${session!.partCount})`,
        });
      }
    };
    await Promise.all(
      Array.from(
        { length: Math.min(MULTIPART_UPLOAD_CONCURRENCY, session.partCount) },
        () => worker(),
      ),
    );

    await apiClient('/admin/ocr/uploads/complete', {
      method: 'POST',
      token,
      signal: request.signal,
      body: JSON.stringify({
        uploadId: session.uploadId,
        objectKey: session.objectKey,
        fileSize: request.file.size,
        parts,
      }),
    });
    uploadCompleted = true;
    onProgress?.({ stage: 'queued', progress: 55, message: '업로드가 완료되어 분석을 시작합니다.' });
    return apiClient<OcrJobCreated>('/admin/ocr/jobs/remote', {
      method: 'POST',
      token,
      signal: request.signal,
      body: JSON.stringify({
        objectKey: session.objectKey,
        fileName: request.file.name,
        fileSize: request.file.size,
        contentType: request.file.type || 'application/octet-stream',
        chunkSize: request.chunkSize,
        overlap: request.overlap,
      }),
    });
  } catch (error) {
    if (session && !uploadCompleted) {
      await apiClient<void>('/admin/ocr/uploads/abort', {
        method: 'POST',
        token,
        body: JSON.stringify({ uploadId: session.uploadId, objectKey: session.objectKey }),
      }).catch(() => undefined);
    }
    throw error;
  }
}

/** Admin UI와 FastAPI 사이의 HTTP 변환 경계입니다. */
export const apiAdminAiService: AdminAiService = {
  async analyzeDocument(request: AnalyzeDocumentRequest, onProgress?: OcrProgressListener) {
    if (request.sourceType === 'url') {
      const job = await createUrlJob(request);
      onProgress?.({ stage: 'queued', progress: 0, message: 'OCR 작업이 대기열에 등록되었습니다.' });
      return pollJob(job, request.signal, onProgress);
    }

    if (request.file.size > OCR_INLINE_FILE_BYTES) {
      const job = await uploadLargeDocument(request, onProgress);
      return pollJob(job, request.signal, onProgress, 55, 45);
    }

    const job = await createFileJob(request);
    onProgress?.({ stage: 'queued', progress: 0, message: 'OCR 작업이 대기열에 등록되었습니다.' });

    // 저장 시 Chunk를 다시 보내지 않고 Backend의 완료된 Job 결과를 참조합니다.
    return pollJob(job, request.signal, onProgress);
  },

  saveDocument(request: SaveDocumentRequest) {
    return apiClient<SaveDocumentResult>('/admin/ocr/vector-save', {
      method: 'POST',
      token: authStorage.getToken(),
      body: JSON.stringify(request),
    });
  },

  listLlmModels(signal?: AbortSignal) {
    return apiClient<LlmModelDefinition[]>('/admin/llm/models', {
      signal,
      token: authStorage.getToken(),
    });
  },

  runLlmModel(request: RunLlmModelRequest) {
    return apiClient<LlmModelResult>('/admin/llm/run', {
      method: 'POST',
      token: authStorage.getToken(),
      body: JSON.stringify({
        prompt: request.prompt,
        modelId: request.modelId,
        documentNames: request.files?.map((file) => file.name) ?? [],
      }),
      signal: request.signal,
    });
  },
};

async function createFileJob(
  request: Extract<AnalyzeDocumentRequest, { sourceType: 'file' }>,
): Promise<OcrJobCreated> {
  const formData = new FormData();
  formData.append('file', request.file);
  formData.append('chunkSize', String(request.chunkSize));
  formData.append('overlap', String(request.overlap));
  return apiClient<OcrJobCreated>('/admin/ocr/jobs', {
    method: 'POST',
    token: authStorage.getToken(),
    body: formData,
    signal: request.signal,
  });
}

async function createUrlJob(
  request: Extract<AnalyzeDocumentRequest, { sourceType: 'url' }>,
): Promise<OcrJobCreated> {
  return apiClient<OcrJobCreated>('/admin/ocr/url-jobs', {
    method: 'POST',
    body: JSON.stringify({
      url: request.url,
      chunkSize: request.chunkSize,
      overlap: request.overlap,
    }),
    signal: request.signal,
    token: authStorage.getToken(),
  });
}
