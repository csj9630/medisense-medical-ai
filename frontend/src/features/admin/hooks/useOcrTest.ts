import { useEffect, useRef, useState } from 'react';
import {
  getOcrOverlap,
  OCR_CHUNK_SIZE,
  OCR_MAX_FILE_BYTES,
  OCR_OVERLAP_PERCENT,
  OCR_SUPPORTED_EXTENSIONS,
  type OcrChunkSize,
  type OcrOverlapPercent,
} from '../constants/adminOptions';
import { adminAiService } from '../services/adminAiService';
import type { AsyncStatus } from '../types/common';
import type { OcrDocumentResult, OcrProgressUpdate } from '../types/ocr';
import {
  describeFileMerge,
  getFileIdentity,
  mergeSelectedFiles,
} from '../../../utils/uploadFiles';

type OcrSourceType = 'file' | 'url';

const messageOf = (error: unknown, fallback = '자료 분석에 실패했습니다.') =>
  error instanceof Error ? error.message : fallback;
const INITIAL_PROGRESS: OcrProgressUpdate = {
  stage: 'idle',
  progress: 0,
  message: '분석 대기 중',
};
const isAbortError = (error: unknown) => error instanceof Error && error.name === 'AbortError';
const isHttpUrl = (value: string) => {
  try {
    const parsed = new URL(value.trim());
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
};

export type OcrBatchItem = {
  id: string;
  file: File;
  status: AsyncStatus;
  result: OcrDocumentResult | null;
  error: string;
  progress: OcrProgressUpdate;
  saveStatus: AsyncStatus;
  saveMessage: string;
};

type WebOcrState = {
  status: AsyncStatus;
  result: OcrDocumentResult | null;
  error: string;
  progress: OcrProgressUpdate;
  saveStatus: AsyncStatus;
  saveMessage: string;
};

const INITIAL_WEB_STATE: WebOcrState = {
  status: 'idle',
  result: null,
  error: '',
  progress: INITIAL_PROGRESS,
  saveStatus: 'idle',
  saveMessage: '',
};

function createItem(file: File): OcrBatchItem {
  return {
    id: getFileIdentity(file),
    file,
    status: 'idle',
    result: null,
    error: '',
    progress: INITIAL_PROGRESS,
    saveStatus: 'idle',
    saveMessage: '',
  };
}

export function useOcrTest() {
  const [sourceType, setSourceTypeState] = useState<OcrSourceType>('file');
  const [items, setItems] = useState<OcrBatchItem[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [selectionError, setSelectionError] = useState('');
  const [url, setUrlState] = useState('');
  const [webState, setWebState] = useState<WebOcrState>(INITIAL_WEB_STATE);
  const [chunkSize, setChunkSize] = useState<OcrChunkSize>(OCR_CHUNK_SIZE);
  const [overlapPercent, setOverlapPercent] = useState<OcrOverlapPercent>(OCR_OVERLAP_PERCENT);
  const analyzeControllers = useRef(new Map<string, AbortController>());
  const webAnalyzeController = useRef<AbortController | null>(null);

  const overlap = getOcrOverlap(chunkSize, overlapPercent);
  const activeItem = items.find((item) => item.id === activeId) ?? items[0] ?? null;
  const fileIsLoading = items.some((item) => item.status === 'loading');
  const fileIsSaving = items.some((item) => item.saveStatus === 'loading');
  const isLoading = fileIsLoading || webState.status === 'loading';
  const isSaving = fileIsSaving || webState.saveStatus === 'loading';
  const isBusy = isLoading || isSaving;

  const status = sourceType === 'file' ? activeItem?.status ?? 'idle' : webState.status;
  const result = sourceType === 'file' ? activeItem?.result ?? null : webState.result;
  const error = sourceType === 'file' ? activeItem?.error ?? '' : webState.error;
  const progress = sourceType === 'file'
    ? activeItem?.progress ?? INITIAL_PROGRESS
    : webState.progress;
  const saveStatus = sourceType === 'file'
    ? activeItem?.saveStatus ?? 'idle'
    : webState.saveStatus;
  const saveMessage = sourceType === 'file'
    ? activeItem?.saveMessage ?? ''
    : webState.saveMessage;
  const canAnalyze = (
    sourceType === 'file' ? items.length > 0 : isHttpUrl(url)
  ) && !isBusy;
  const canSave = Boolean(
    status === 'success'
    && result
    && saveStatus !== 'loading'
    && saveStatus !== 'success'
    && !isBusy,
  );

  useEffect(
    () => () => {
      analyzeControllers.current.forEach((controller) => controller.abort());
      webAnalyzeController.current?.abort();
    },
    [],
  );

  function updateItem(id: string, update: (item: OcrBatchItem) => OcrBatchItem) {
    setItems((current) => current.map((item) => (item.id === id ? update(item) : item)));
  }

  function selectFiles(nextFiles: File[]) {
    const merged = mergeSelectedFiles(
      items.map((item) => item.file),
      nextFiles,
      OCR_SUPPORTED_EXTENSIONS,
      undefined,
      OCR_MAX_FILE_BYTES,
    );
    const currentById = new Map(items.map((item) => [item.id, item]));
    const nextItems = merged.files.map(
      (file) => currentById.get(getFileIdentity(file)) ?? createItem(file),
    );
    setItems(nextItems);
    setActiveId((current) => (
      current && nextItems.some((item) => item.id === current)
        ? current
        : nextItems[0]?.id ?? null
    ));
    setSelectionError(describeFileMerge(
      merged,
      'PDF, PNG, JPG, DOCX, PPTX, JSON, JSONL, CSV, TXT, ZIP',
      '8GB',
    ));
  }

  function removeFile(id: string) {
    analyzeControllers.current.get(id)?.abort();
    analyzeControllers.current.delete(id);
    const nextItems = items.filter((item) => item.id !== id);
    setItems(nextItems);
    if (activeId === id) setActiveId(nextItems[0]?.id ?? null);
    setSelectionError('');
  }

  function setSourceType(nextSourceType: OcrSourceType) {
    if (nextSourceType === sourceType || isBusy) return;
    setSourceTypeState(nextSourceType);
  }

  function setUrl(nextUrl: string) {
    webAnalyzeController.current?.abort();
    webAnalyzeController.current = null;
    setUrlState(nextUrl);
    setWebState(INITIAL_WEB_STATE);
  }

  async function analyzeItem(item: OcrBatchItem) {
    const controller = new AbortController();
    analyzeControllers.current.set(item.id, controller);
    updateItem(item.id, (current) => ({
      ...current,
      status: 'loading',
      result: null,
      error: '',
      saveStatus: 'idle',
      saveMessage: '',
      progress: { stage: 'uploading', progress: 0, message: '문서를 업로드하고 있습니다.' },
    }));
    try {
      const analyzedResult = await adminAiService.analyzeDocument(
        {
          sourceType: 'file',
          file: item.file,
          chunkSize,
          overlap,
          signal: controller.signal,
        },
        (nextProgress) => updateItem(
          item.id,
          (current) => ({ ...current, progress: nextProgress }),
        ),
      );
      updateItem(item.id, (current) => ({
        ...current,
        result: analyzedResult,
        status: 'success',
        progress: { stage: 'completed', progress: 100, message: '문서 분석이 완료되었습니다.' },
      }));
    } catch (unknownError) {
      if (isAbortError(unknownError)) return;
      updateItem(item.id, (current) => ({
        ...current,
        error: messageOf(unknownError),
        status: 'error',
        progress: { ...current.progress, stage: 'failed', message: '문서 분석에 실패했습니다.' },
      }));
    } finally {
      if (analyzeControllers.current.get(item.id) === controller) {
        analyzeControllers.current.delete(item.id);
      }
    }
  }

  async function analyzeUrl() {
    const controller = new AbortController();
    webAnalyzeController.current = controller;
    setWebState({
      ...INITIAL_WEB_STATE,
      status: 'loading',
      progress: {
        stage: 'validating_url',
        progress: 0,
        message: '웹페이지 주소를 확인하고 있습니다.',
      },
    });
    try {
      const analyzedResult = await adminAiService.analyzeDocument(
        {
          sourceType: 'url',
          url: url.trim(),
          chunkSize,
          overlap,
          signal: controller.signal,
        },
        (nextProgress) => setWebState(
          (current) => ({ ...current, progress: nextProgress }),
        ),
      );
      setWebState((current) => ({
        ...current,
        result: analyzedResult,
        status: 'success',
        progress: { stage: 'completed', progress: 100, message: '웹페이지 분석이 완료되었습니다.' },
      }));
    } catch (unknownError) {
      if (isAbortError(unknownError)) return;
      setWebState((current) => ({
        ...current,
        error: messageOf(unknownError, '웹페이지 분석에 실패했습니다.'),
        status: 'error',
        progress: { ...current.progress, stage: 'failed', message: '웹페이지 분석에 실패했습니다.' },
      }));
    } finally {
      if (webAnalyzeController.current === controller) {
        webAnalyzeController.current = null;
      }
    }
  }

  async function analyze() {
    if (!canAnalyze) return;
    if (sourceType === 'url') {
      await analyzeUrl();
      return;
    }
    setSelectionError('');
    await Promise.all(items.map(analyzeItem));
  }

  async function save() {
    if (!canSave || !result) return;

    if (sourceType === 'url') {
      setWebState((current) => ({ ...current, saveStatus: 'loading', saveMessage: '' }));
      try {
        const response = await adminAiService.saveDocument({ jobId: result.jobId });
        setWebState((current) => ({
          ...current,
          saveMessage: response.message,
          saveStatus: 'success',
        }));
      } catch (unknownError) {
        setWebState((current) => ({
          ...current,
          saveMessage: messageOf(unknownError, '웹페이지를 VectorDB에 저장하지 못했습니다.'),
          saveStatus: 'error',
        }));
      }
      return;
    }

    if (!activeItem) return;
    const itemId = activeItem.id;
    updateItem(itemId, (current) => ({ ...current, saveStatus: 'loading', saveMessage: '' }));
    try {
      const response = await adminAiService.saveDocument({ jobId: result.jobId });
      updateItem(itemId, (current) => ({
        ...current,
        saveMessage: response.message,
        saveStatus: 'success',
      }));
    } catch (unknownError) {
      updateItem(itemId, (current) => ({
        ...current,
        saveMessage: messageOf(unknownError, '문서를 VectorDB에 저장하지 못했습니다.'),
        saveStatus: 'error',
      }));
    }
  }

  return {
    sourceType,
    items,
    activeItem,
    activeId,
    selectionError,
    url,
    status,
    result,
    error,
    progress,
    saveStatus,
    saveMessage,
    isLoading,
    isSaving,
    isBusy,
    canAnalyze,
    canSave,
    chunkSize,
    overlap,
    overlapPercent,
    setSourceType,
    selectFiles,
    removeFile,
    setActiveId,
    setUrl,
    setChunkSize,
    setOverlapPercent,
    analyze,
    save,
  };
}
