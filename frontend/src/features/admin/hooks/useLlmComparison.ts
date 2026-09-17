import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { adminAiService } from "../services/adminAiService";
import type {
  LlmModelDefinition,
  LlmModelRunMap,
} from "../types/llm";

function createInitialModelRuns(models: readonly LlmModelDefinition[]): LlmModelRunMap {
  return Object.fromEntries(
    models.map((model) => [
      model.id,
      { modelId: model.id, status: "idle" as const },
    ]),
  );
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}

export function useLlmComparison() {
  const [models, setModels] = useState<LlmModelDefinition[]>([]);
  const [isLoadingModels, setIsLoadingModels] = useState(true);
  const [modelLoadError, setModelLoadError] = useState("");
  const [prompt, setPrompt] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [modelRuns, setModelRuns] = useState<LlmModelRunMap>({});
  const [isRunningAll, setIsRunningAll] = useState(false);
  const [error, setError] = useState("");

  const controllersRef = useRef(new Map<string, AbortController>());
  const requestVersionsRef = useRef(new Map<string, number>());
  const allRunVersionRef = useRef(0);
  const allRunActiveRef = useRef(false);
  const modelListControllerRef = useRef<AbortController | null>(null);

  const loadModels = useCallback(async () => {
    modelListControllerRef.current?.abort();
    const controller = new AbortController();
    modelListControllerRef.current = controller;
    setIsLoadingModels(true);
    setModelLoadError("");
    try {
      const nextModels = await adminAiService.listLlmModels(controller.signal);
      setModels(nextModels);
      setModelRuns(createInitialModelRuns(nextModels));
    } catch (loadError) {
      if (isAbortError(loadError)) return;
      setModels([]);
      setModelRuns({});
      setModelLoadError(
        loadError instanceof Error
          ? loadError.message
          : "LLM 모델 목록을 불러오지 못했습니다.",
      );
    } finally {
      if (modelListControllerRef.current === controller) {
        modelListControllerRef.current = null;
        setIsLoadingModels(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadModels();
    return () => modelListControllerRef.current?.abort();
  }, [loadModels]);

  const runnableModels = useMemo(
    () => models.filter((model) => model.enabled && model.available),
    [models],
  );
  const hasRunningModels = useMemo(
    () => Object.values(modelRuns).some((run) => run.status === "running"),
    [modelRuns],
  );

  useEffect(
    () => () => {
      allRunVersionRef.current += 1;
      allRunActiveRef.current = false;
      controllersRef.current.forEach((controller, modelId) => {
        requestVersionsRef.current.set(
          modelId,
          (requestVersionsRef.current.get(modelId) ?? 0) + 1,
        );
        controller.abort();
      });
      controllersRef.current.clear();
    },
    [],
  );

  const executeModel = useCallback(
    async (modelId: string, runPrompt: string, referenceFiles: File[]) => {
      controllersRef.current.get(modelId)?.abort();
      const requestVersion = (requestVersionsRef.current.get(modelId) ?? 0) + 1;
      requestVersionsRef.current.set(modelId, requestVersion);
      const controller = new AbortController();
      const startedAt = Date.now();
      controllersRef.current.set(modelId, controller);
      setModelRuns((current) => ({
        ...current,
        [modelId]: { modelId, status: "running", startedAt },
      }));

      try {
        const result = await adminAiService.runLlmModel({
          prompt: runPrompt,
          modelId,
          files: referenceFiles,
          signal: controller.signal,
        });
        if (requestVersionsRef.current.get(modelId) !== requestVersion) return;
        setModelRuns((current) => ({
          ...current,
          [modelId]: {
            modelId,
            status: "success",
            answer: result.answer,
            responseTimeSeconds: result.responseTimeSeconds,
            inputTokens: result.inputTokens,
            outputTokens: result.outputTokens,
            totalTokens: result.totalTokens,
            provider: result.provider,
            providerModel: result.providerModel,
            isMock: result.isMock,
            finishReason: result.finishReason,
          },
        }));
      } catch (unknownError) {
        if (requestVersionsRef.current.get(modelId) !== requestVersion) return;
        setModelRuns((current) => ({
          ...current,
          [modelId]: {
            modelId,
            status: isAbortError(unknownError) ? "cancelled" : "error",
            error: isAbortError(unknownError)
              ? "실행이 취소되었습니다. Provider 추론은 계속될 수 있습니다."
              : unknownError instanceof Error
                ? unknownError.message
                : "모델 실행 중 오류가 발생했습니다.",
            responseTimeSeconds: (Date.now() - startedAt) / 1_000,
          },
        }));
      } finally {
        if (requestVersionsRef.current.get(modelId) === requestVersion) {
          controllersRef.current.delete(modelId);
        }
      }
    },
    [],
  );

  const runModel = useCallback(
    async (modelId: string, sharedPrompt = prompt, sharedFiles: File[] = files) => {
      const model = models.find((candidate) => candidate.id === modelId);
      if (!model?.enabled || !model.available) {
        setError(model?.availabilityMessage ?? "현재 실행할 수 없는 모델입니다.");
        return;
      }
      const runPrompt = sharedPrompt.trim();
      if (!runPrompt) {
        setError("비교할 공통 질문을 입력해 주세요.");
        return;
      }
      setError("");
      await executeModel(modelId, runPrompt, sharedFiles);
    },
    [executeModel, files, models, prompt],
  );

  const runAllModels = useCallback(async () => {
    if (allRunActiveRef.current || hasRunningModels) return;
    const runPrompt = prompt.trim();
    if (!runPrompt) {
      setError("비교할 공통 질문을 입력해 주세요.");
      return;
    }
    if (runnableModels.length === 0) {
      setError("현재 실행 가능한 LLM 모델이 없습니다.");
      return;
    }
    const allRunVersion = allRunVersionRef.current + 1;
    allRunVersionRef.current = allRunVersion;
    allRunActiveRef.current = true;
    setError("");
    setIsRunningAll(true);
    await Promise.allSettled(
      runnableModels.map((model) => runModel(model.id, runPrompt, files)),
    );
    if (allRunVersionRef.current === allRunVersion) {
      allRunActiveRef.current = false;
      setIsRunningAll(false);
    }
  }, [files, hasRunningModels, prompt, runModel, runnableModels]);

  const cancelModel = useCallback((modelId: string) => {
    const controller = controllersRef.current.get(modelId);
    if (!controller) return;
    requestVersionsRef.current.set(modelId, (requestVersionsRef.current.get(modelId) ?? 0) + 1);
    controller.abort();
    controllersRef.current.delete(modelId);
    setModelRuns((current) => {
      const running = current[modelId];
      if (!running || running.status !== "running") return current;
      return {
        ...current,
        [modelId]: {
          modelId,
          status: "cancelled",
          error: "실행이 취소되었습니다. Provider 추론은 계속될 수 있습니다.",
          responseTimeSeconds: running.startedAt
            ? (Date.now() - running.startedAt) / 1_000
            : undefined,
        },
      };
    });
  }, []);

  const reset = useCallback(() => {
    allRunVersionRef.current += 1;
    allRunActiveRef.current = false;
    controllersRef.current.forEach((controller, modelId) => {
      requestVersionsRef.current.set(modelId, (requestVersionsRef.current.get(modelId) ?? 0) + 1);
      controller.abort();
    });
    controllersRef.current.clear();
    setPrompt("");
    setFiles([]);
    setModelRuns(createInitialModelRuns(models));
    setError("");
    setIsRunningAll(false);
  }, [models]);

  return {
    models,
    isLoadingModels,
    modelLoadError,
    reloadModels: loadModels,
    prompt,
    setPrompt,
    files,
    setFiles,
    modelRuns,
    isRunningAll,
    hasRunningModels,
    hasRunnableModels: runnableModels.length > 0,
    error,
    runModel,
    runAllModels,
    cancelModel,
    reset,
  };
}
