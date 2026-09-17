import { apiClient } from '../services/apiClient';
import { withChatToken } from '../features/auth/guestSession';

export interface RagSearchResult {
  chunkId: string | null;
  documentId: string | null;
  content: string;
  score: number;
  source: string | null;
  metadata: Record<string, unknown> | null;
}

interface RagSearchResultDto {
  chunk_id: string | null;
  document_id: string | null;
  content: string;
  score: number;
  source: string | null;
  metadata: Record<string, unknown> | null;
}

interface RagSearchResponseDto {
  query: string;
  results: RagSearchResultDto[];
}

function toResult(dto: RagSearchResultDto): RagSearchResult {
  return {
    chunkId: dto.chunk_id,
    documentId: dto.document_id,
    content: dto.content,
    score: dto.score,
    source: dto.source,
    metadata: dto.metadata,
  };
}

export async function searchRagDocuments(
  query: string,
  options?: { topK?: number; useReranker?: boolean },
): Promise<RagSearchResult[]> {
  const dto = await withChatToken((token) =>
    apiClient<RagSearchResponseDto>('/rag/search', {
      method: 'POST',
      token,
      body: JSON.stringify({
        query,
        top_k: options?.topK ?? 5,
        use_reranker: options?.useReranker ?? false,
      }),
    }),
  );
  return dto.results.map(toResult);
}
