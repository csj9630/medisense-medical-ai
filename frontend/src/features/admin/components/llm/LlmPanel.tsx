import { useLlmComparison } from "../../hooks/useLlmComparison";
import { LlmResultGrid } from "./LlmResultGrid";
import { LlmTestForm } from "./LlmTestForm";

export function LlmPanel() {
  const llm = useLlmComparison();
  const realModelCount = llm.models.filter((model) => !model.isMock).length;
  const mockModelCount = llm.models.filter((model) => model.isMock).length;

  return (
    <section className="admin-workspace" aria-labelledby="llm-panel-title">
      <div className="admin-section-heading">
        <div>
          <span className="admin-eyebrow">MODEL COMPARISON LAB</span>
          <h2 id="llm-panel-title">LLM 응답 비교</h2>
          <p>
            Gemma·MedGemma 최종·MedGemma 데이터셋·Qwen·Llama 다섯 모델에
            같은 질문을 전달해 응답과 실행 지표를 비교합니다.
          </p>
        </div>
        <span className="mock-badge">
          Real {realModelCount} · Mock {mockModelCount}
        </span>
      </div>

      <p className="llm-provider-notice">
        모든 모델 실행 시 입력한 질문은 Vast.ai 추론 서버로 전송됩니다. 민감한
        의료·개인정보를 입력하지 마세요. 선택한 참고 파일은 아직 업로드되지
        않으며 파일명만 조건으로 전달됩니다.
      </p>

      <LlmTestForm
        prompt={llm.prompt}
        files={llm.files}
        isRunningAll={llm.isRunningAll}
        hasRunningModels={llm.hasRunningModels}
        isLoadingModels={llm.isLoadingModels}
        hasRunnableModels={llm.hasRunnableModels}
        error={llm.error}
        onPromptChange={llm.setPrompt}
        onFilesChange={llm.setFiles}
        onRunAll={() => void llm.runAllModels()}
        onReset={llm.reset}
      />

      <LlmResultGrid
        models={llm.models}
        modelRuns={llm.modelRuns}
        isLoading={llm.isLoadingModels}
        loadError={llm.modelLoadError}
        onReload={() => void llm.reloadModels()}
        onRunModel={(modelId) => void llm.runModel(modelId)}
        onCancelModel={llm.cancelModel}
      />
    </section>
  );
}
