export type LlmModelGroup = "main" | "other";

export type LlmRunStatus =
  | "idle"
  | "running"
  | "success"
  | "error"
  | "cancelled";

export type LlmModelDefinition = {
  id: string;
  label: string;
  family: string;
  trainingStage: string;
  description: string;
  group: LlmModelGroup;
  provider: string;
  providerModel: string;
  enabled: boolean;
  available: boolean;
  availabilityMessage: string | null;
  isMock: boolean;
};

export type RunLlmModelRequest = {
  prompt: string;
  modelId: string;
  files?: File[];
  signal?: AbortSignal;
};

export type LlmModelResult = {
  modelId: string;
  provider: string;
  providerModel: string;
  answer: string;
  responseTimeSeconds: number;
  inputTokens: number | null;
  outputTokens: number | null;
  totalTokens: number | null;
  finishReason: string | null;
  isMock: boolean;
};

export type LlmModelRun = {
  modelId: string;
  status: LlmRunStatus;
  answer?: string;
  error?: string;
  responseTimeSeconds?: number;
  inputTokens?: number | null;
  outputTokens?: number | null;
  totalTokens?: number | null;
  provider?: string;
  providerModel?: string;
  isMock?: boolean;
  finishReason?: string | null;
  startedAt?: number;
};

export type LlmModelRunMap = Record<string, LlmModelRun>;
