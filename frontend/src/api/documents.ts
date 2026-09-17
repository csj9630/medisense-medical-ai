import { apiClient } from '../services/apiClient';
import { withChatToken } from '../features/auth/guestSession';

interface OcrLineDto {
  text: string;
  confidence: number;
}

interface OcrResponseDto {
  text: string;
  lines: OcrLineDto[];
}

/**
 * 이미지에서 텍스트를 추출한다 (DocumentPreviewPanel에서 호출).
 * 파일은 서버에 저장되지 않고 OCR 결과만 즉시 돌아온다.
 */
export async function extractTextFromImage(file: File): Promise<OcrResponseDto> {
  const formData = new FormData();
  formData.append('file', file);
  return withChatToken((token) =>
    apiClient<OcrResponseDto>('/documents/ocr', { method: 'POST', token, body: formData }),
  );
}
