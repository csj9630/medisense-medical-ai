import type { LlmModelDefinition, LlmModelResult, RunLlmModelRequest } from '../types/llm';
import type {
  AnalyzeDocumentRequest,
  OcrDocumentResult,
  OcrProgressListener,
  SaveDocumentRequest,
  SaveDocumentResult,
} from '../types/ocr';
import { apiAdminAiService } from './apiAdminAiService';

export interface AdminAiService {
  analyzeDocument(request: AnalyzeDocumentRequest, onProgress?: OcrProgressListener): Promise<OcrDocumentResult>;
  saveDocument(request: SaveDocumentRequest): Promise<SaveDocumentResult>;
  listLlmModels(signal?: AbortSignal): Promise<LlmModelDefinition[]>;
  runLlmModel(request: RunLlmModelRequest): Promise<LlmModelResult>;
}

// UI와 Hook은 OCR·LLM의 HTTP 세부사항을 알지 않고 이 계약만 사용합니다.
export const adminAiService: AdminAiService = apiAdminAiService;
