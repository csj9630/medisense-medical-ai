import { apiClient } from '../services/apiClient';
import { withChatToken } from '../features/auth/guestSession';
import type { Conversation } from './types';

// 백엔드 응답은 DB 컬럼명 그대로 snake_case로 온다 (app/schemas/conversation.py 참고).
// 화면 쪽 코드가 쓰는 camelCase 타입(Conversation)으로는 여기서만 변환한다.
interface ConversationDto {
  id: string;
  title: string | null;
  is_title_custom: boolean;
  category: string | null;
  updated_at: string;
}

function toConversation(dto: ConversationDto): Conversation {
  return {
    id: dto.id,
    title: dto.title ?? '새 대화',
    isTitleCustom: dto.is_title_custom,
    category: dto.category ?? undefined,
    updatedAt: dto.updated_at,
  };
}

export async function getConversations(): Promise<Conversation[]> {
  const list = await withChatToken((token) => apiClient<ConversationDto[]>('/conversations', { token }));
  return list.map(toConversation);
}

// 제목/카테고리(진료과)/대화 내용을 한 번에 검색한다(모드 구분 없음) - 사이드바 검색창.
export async function searchConversations(query: string): Promise<Conversation[]> {
  const list = await withChatToken((token) =>
    apiClient<ConversationDto[]>(`/conversations/search?q=${encodeURIComponent(query)}`, { token }),
  );
  return list.map(toConversation);
}

export async function createConversation(): Promise<Conversation> {
  const dto = await withChatToken((token) =>
    apiClient<ConversationDto>('/conversations', { method: 'POST', token }),
  );
  return toConversation(dto);
}

export async function renameConversation(id: string, title: string): Promise<void> {
  await withChatToken((token) =>
    apiClient(`/conversations/${id}`, {
      method: 'PATCH',
      token,
      body: JSON.stringify({ title }),
    }),
  );
}

export async function deleteConversation(id: string): Promise<void> {
  await withChatToken((token) => apiClient(`/conversations/${id}`, { method: 'DELETE', token }));
}
