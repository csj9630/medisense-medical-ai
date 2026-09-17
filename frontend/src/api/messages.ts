import { apiClient } from '../services/apiClient';
import { withChatToken } from '../features/auth/guestSession';
import type { Message, MessageAttachment } from './types';

interface MessageAttachmentDto {
  id: string;
  file_name: string;
  file_type: string | null;
  file_size_bytes: number | null;
}

interface MessageDto {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  attachments: MessageAttachmentDto[];
}

function toAttachment(dto: MessageAttachmentDto): MessageAttachment {
  return { name: dto.file_name, type: dto.file_type ?? undefined, size: dto.file_size_bytes ?? undefined };
}

function toMessage(dto: MessageDto): Message {
  return {
    id: dto.id,
    role: dto.role,
    content: dto.content,
    createdAt: dto.created_at,
    attachments: dto.attachments?.length ? dto.attachments.map(toAttachment) : undefined,
  };
}

export async function getMessages(conversationId: string): Promise<Message[]> {
  const list = await withChatToken((token) =>
    apiClient<MessageDto[]>(`/conversations/${conversationId}/messages`, { token }),
  );
  return list.map(toMessage);
}

/**
 * 사용자 메시지를 저장하고 assistant 응답을 받아온다.
 * 반환값은 assistant 응답 메시지 하나다 (사용자 메시지는 화면에서 낙관적으로 먼저 렌더링됨).
 *
 * 첨부파일이 있으면 multipart로 원본을 서버에 전송해 검증한다. 현재 원본을 영구
 * 저장하지는 않고 안전한 메타데이터만 메시지에 남긴다.
 */
export async function sendMessage(
  conversationId: string,
  content: string,
  files?: File[],
  modelId?: string,
): Promise<Message> {
  if (files?.length) {
    const formData = new FormData();
    formData.append('content', content);
    if (modelId) formData.append('modelId', modelId);
    files.forEach((file) => formData.append('files', file));

    const dto = await withChatToken((token) =>
      apiClient<MessageDto>(`/conversations/${conversationId}/messages/upload`, {
        method: 'POST',
        token,
        body: formData,
      }),
    );
    return toMessage(dto);
  }

  const dto = await withChatToken((token) =>
    apiClient<MessageDto>(`/conversations/${conversationId}/messages`, {
      method: 'POST',
      token,
      body: JSON.stringify({
        content,
        attachments: [],
        // ModelSelect가 Backend의 Vast.ai Model Registry와 같은 ID를 사용한다.
        model_id: modelId,
      }),
    }),
  );
  return toMessage(dto);
}
