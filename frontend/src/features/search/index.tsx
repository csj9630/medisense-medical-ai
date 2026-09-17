import { useState } from 'react';
import { Loader2, Search } from 'lucide-react';
import { searchRagDocuments } from '../../api/rag';
import type { RagSearchResult } from '../../api/rag';
import { ApiError } from '../../services/apiClient';

export function SearchPage() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<RagSearchResult[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed || loading) return;

    setLoading(true);
    setError(null);
    try {
      const found = await searchRagDocuments(trimmed);
      setResults(found);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '검색에 실패했어요. 잠시 후 다시 시도해주세요.');
      setResults(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col gap-4 px-6 py-8">
      <div>
        <h1 className="text-lg font-semibold text-neutral-800 dark:text-neutral-100">근거 문서 검색</h1>
        <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
          RAG 지식베이스에 저장된 의료 문서를 직접 검색해봅니다. 채팅 응답이 참고하는 것과 같은
          검색 결과입니다.
        </p>
      </div>

      <form onSubmit={handleSearch} className="flex gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="예: 두통 원인, 소아 발열 대처법"
          className="flex-1 rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-400 dark:border-neutral-700 dark:bg-neutral-800 dark:text-neutral-100"
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {loading ? <Loader2 size={15} className="animate-spin" /> : <Search size={15} />}
          검색
        </button>
      </form>

      {error && (
        <p className="text-sm text-red-500" role="alert">
          {error}
        </p>
      )}

      {results && results.length === 0 && !error && (
        <p className="text-sm text-neutral-400 dark:text-neutral-500">
          일치하는 문서를 찾지 못했어요. 아직 RAG 지식베이스에 저장된 문서가 없을 수도 있어요.
        </p>
      )}

      {results && results.length > 0 && (
        <div className="flex flex-col gap-3">
          {results.map((result, index) => (
            <div
              key={result.chunkId ?? index}
              className="rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-700 dark:bg-neutral-800"
            >
              <div className="mb-1.5 flex items-center justify-between text-xs text-neutral-400 dark:text-neutral-500">
                <span>{result.source ?? '출처 미상'}</span>
                <span>유사도 {result.score.toFixed(3)}</span>
              </div>
              <p className="whitespace-pre-wrap text-sm text-neutral-700 dark:text-neutral-200">
                {result.content}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
