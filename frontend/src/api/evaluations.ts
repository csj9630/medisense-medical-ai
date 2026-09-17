import { apiClient } from '../services/apiClient';
import { authStorage } from '../features/auth/authStorage';

export interface RetrievalEvalResult {
  numQueries: number;
  recallAtK: Record<string, number>;
  mrr: number;
  datasetName: string;
}

export interface GroundTruthCase {
  id: string;
  question: string;
  expectedAnswer: string;
}

export interface GroundTruthParseResponse {
  sourceName: string;
  cases: GroundTruthCase[];
}

export interface AnswerEvaluationInput extends GroundTruthCase {
  predictedAnswer: string;
}

export interface AnswerEvaluationCaseResult extends AnswerEvaluationInput {
  exactMatch: number;
  tokenF1: number;
  characterSimilarity: number;
}

export interface AnswerEvaluationResponse {
  caseCount: number;
  exactMatch: number;
  tokenF1: number;
  characterSimilarity: number;
  results: AnswerEvaluationCaseResult[];
}

/**
 * corpus/쿼리 임베딩을 새로 계산하므로(캐시 없음) 수십 초~수 분 걸릴 수 있다 —
 * 호출하는 쪽에서 반드시 로딩 상태를 보여줘야 한다.
 */
export function runRetrievalEvaluation(signal?: AbortSignal): Promise<RetrievalEvalResult> {
  return apiClient<RetrievalEvalResult>('/admin/evaluations/retrieval', {
    signal,
    token: authStorage.getToken(),
  });
}

export function parseGroundTruth(input: {
  text?: string;
  file?: File;
}): Promise<GroundTruthParseResponse> {
  const formData = new FormData();
  if (input.file) formData.append('file', input.file);
  else formData.append('text', input.text ?? '');

  return apiClient<GroundTruthParseResponse>('/evaluations/ground-truth/parse', {
    method: 'POST',
    body: formData,
  });
}

export function runAnswerEvaluation(
  cases: AnswerEvaluationInput[],
): Promise<AnswerEvaluationResponse> {
  return apiClient<AnswerEvaluationResponse>('/evaluations/answers/run', {
    method: 'POST',
    body: JSON.stringify({ cases }),
  });
}
