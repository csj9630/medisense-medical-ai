import type {
  LlmModelDefinition,
  LlmModelRunMap,
} from "../../types/llm";
import { LlmResultCard } from "./LlmResultCard";

type Props = {
  models: readonly LlmModelDefinition[];
  modelRuns: LlmModelRunMap;
  isLoading: boolean;
  loadError: string;
  onReload: () => void;
  onRunModel: (modelId: string) => void;
  onCancelModel: (modelId: string) => void;
};

function ModelGroup({
  models,
  className,
  modelRuns,
  onRunModel,
  onCancelModel,
}: Pick<Props, "modelRuns" | "onRunModel" | "onCancelModel"> & {
  models: readonly LlmModelDefinition[];
  className: string;
}) {
  return (
    <div className={className}>
      {models.map((model) => (
        <LlmResultCard
          key={model.id}
          model={model}
          run={modelRuns[model.id] ?? { modelId: model.id, status: "idle" }}
          onRun={() => onRunModel(model.id)}
          onCancel={() => onCancelModel(model.id)}
        />
      ))}
    </div>
  );
}

export function LlmResultGrid(props: Props) {
  const isBusy = Object.values(props.modelRuns).some(
    (run) => run.status === "running",
  );

  if (props.isLoading) {
    return (
      <div className="admin-card llm-model-loading">
        LLM Provider 상태를 확인하고 있습니다...
      </div>
    );
  }

  if (props.loadError) {
    return (
      <div className="admin-card llm-model-loading" role="alert">
        <p>{props.loadError}</p>
        <button
          className="admin-secondary-button"
          type="button"
          onClick={props.onReload}
        >
          모델 목록 다시 불러오기
        </button>
      </div>
    );
  }

  const mainModels = props.models.filter((model) => model.group === "main");
  const otherModels = props.models.filter((model) => model.group === "other");

  return (
    <div className="llm-comparison-results" aria-busy={isBusy}>
      <section
        className="llm-comparison-section"
        aria-labelledby="main-model-comparison-title"
      >
        <div className="llm-group-heading">
          <span>REAL PROVIDERS</span>
          <h3 id="main-model-comparison-title">Gemma 계열</h3>
          <p>한국어 의료 Gemma와 MedGemma 최종·데이터셋 LoRA를 비교합니다.</p>
        </div>
        <ModelGroup
          {...props}
          models={mainModels}
          className="llm-model-grid main-model-grid"
        />
      </section>

      <section
        className="llm-comparison-section"
        aria-labelledby="other-model-comparison-title"
      >
        <div className="llm-group-heading">
          <span>VAST.AI · 2× V100</span>
          <h3 id="other-model-comparison-title">원격 의료 LLM</h3>
          <p>Vast.ai에서 실행하는 Qwen과 Llama QLoRA 모델입니다.</p>
        </div>
        <ModelGroup
          {...props}
          models={otherModels}
          className="llm-model-grid other-model-grid"
        />
      </section>
    </div>
  );
}
