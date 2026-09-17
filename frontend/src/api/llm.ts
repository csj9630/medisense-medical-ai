import { apiClient } from '../services/apiClient';

export type LlmModel = {
  id: string;
  label: string;
  description: string;
};

type LlmModelDto = {
  model_id: string;
  label: string;
  description: string;
};

/** Backend의 공통 LLM Registry를 조회한다. 원격 API Key는 응답에 포함되지 않는다. */
export async function getLlmModels(): Promise<LlmModel[]> {
  const models = await apiClient<LlmModelDto[]>('/llm/models');
  return models.map((model) => ({
    id: model.model_id,
    label: model.label,
    description: model.description,
  }));
}
