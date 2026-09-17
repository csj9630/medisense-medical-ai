import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { getLlmModels } from '../../api/llm';
import {
  DEFAULT_MODEL_ID,
  FALLBACK_MODEL_OPTIONS,
  toModelOptions,
  type ModelOption,
} from './modelOptions';

type ModelSelectContextValue = {
  modelId: string;
  modelOptions: ModelOption[];
  setModelId: (id: string) => void;
};

const ModelSelectContext = createContext<ModelSelectContextValue | null>(null);
const STORAGE_KEY = 'thegpt-selected-model';

function getInitialModelId() {
  const stored = localStorage.getItem(STORAGE_KEY);
  return FALLBACK_MODEL_OPTIONS.some((option) => option.id === stored) ? stored! : DEFAULT_MODEL_ID;
}

// 홈 화면에서 고른 모델이 채팅 화면으로 넘어가도 유지되도록 컨텍스트로 공유한다.
// modelId는 그대로 api/messages.ts의 sendMessage()를 통해 백엔드로 전달된다.
export function ModelSelectProvider({ children }: { children: ReactNode }) {
  const [modelId, setModelIdState] = useState(getInitialModelId);
  const [modelOptions, setModelOptions] = useState<ModelOption[]>(FALLBACK_MODEL_OPTIONS);

  useEffect(() => {
    let cancelled = false;

    getLlmModels()
      .then((models) => {
        if (cancelled || models.length === 0) return;

        const nextOptions = toModelOptions(models);
        setModelOptions(nextOptions);
        setModelIdState((current) => {
          if (nextOptions.some((option) => option.id === current)) return current;

          const fallback = nextOptions.find((option) => option.id === DEFAULT_MODEL_ID) ?? nextOptions[0];
          localStorage.setItem(STORAGE_KEY, fallback.id);
          return fallback.id;
        });
      })
      // Backend 기동 전에도 홈을 열 수 있도록 로컬 fallback 목록을 유지한다.
      .catch(() => undefined);

    return () => {
      cancelled = true;
    };
  }, []);

  function setModelId(id: string) {
    if (!modelOptions.some((option) => option.id === id)) return;
    setModelIdState(id);
    localStorage.setItem(STORAGE_KEY, id);
  }

  return (
    <ModelSelectContext.Provider value={{ modelId, modelOptions, setModelId }}>
      {children}
    </ModelSelectContext.Provider>
  );
}

export function useModelSelect() {
  const context = useContext(ModelSelectContext);
  if (!context) throw new Error('useModelSelect는 ModelSelectProvider 안에서만 사용할 수 있습니다.');
  return context;
}
