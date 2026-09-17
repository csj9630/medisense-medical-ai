import type { LlmModel } from '../../api/llm';

export type ModelTier = 'recommended' | 'beta';

export type ModelOption = {
  id: string;
  label: string;
  tier: ModelTier;
};

export const DEFAULT_MODEL_ID = 'medgemma';

// Backend가 아직 실행 중이 아니거나 모델 목록 조회가 실패해도 입력창은 계속 쓸 수
// 있어야 한다. 정상 실행 시에는 ModelSelectContext가 /api/llm/models 결과로 교체한다.
export const FALLBACK_MODEL_OPTIONS: ModelOption[] = [
  { id: 'medgemma', label: 'MedGemma 2.0', tier: 'recommended' },
  { id: 'medgemma-dataset', label: 'MedGemma 1.0', tier: 'beta' },
  { id: 'gemma', label: 'Gemma Medical', tier: 'beta' },
  { id: 'qwen', label: 'Qwen', tier: 'beta' },
  { id: 'llama', label: 'Llama', tier: 'beta' },
];

export function toModelOptions(models: LlmModel[]): ModelOption[] {
  return models.map((model) => ({
    id: model.id,
    label: model.label,
    tier: model.id === DEFAULT_MODEL_ID ? 'recommended' : 'beta',
  }));
}

export function getModelOption(id: string, options: ModelOption[]): ModelOption {
  return options.find((option) => option.id === id) ?? options[0] ?? FALLBACK_MODEL_OPTIONS[0];
}
