import { useEffect, useState } from "react";
import {
  Ban,
  Check,
  Clipboard,
  LoaderCircle,
  Play,
  RotateCcw,
  TriangleAlert,
} from "lucide-react";
import type {
  LlmModelDefinition,
  LlmModelRun,
  LlmRunStatus,
} from "../../types/llm";

const STATUS_LABELS: Record<LlmRunStatus, string> = {
  idle: "대기",
  running: "실행 중",
  success: "완료",
  error: "오류",
  cancelled: "취소",
};

function StatusIcon({ status }: { status: LlmRunStatus }) {
  if (status === "running") return <LoaderCircle className="spin" size={13} />;
  if (status === "success") return <Check size={13} />;
  if (status === "error") return <TriangleAlert size={13} />;
  if (status === "cancelled") return <Ban size={13} />;
  return <span className="model-idle-dot" aria-hidden="true" />;
}

type Props = {
  model: LlmModelDefinition;
  run: LlmModelRun;
  onRun: () => void;
  onCancel: () => void;
};

export function LlmResultCard({ model, run, onRun, onCancel }: Props) {
  const [copied, setCopied] = useState(false);
  const [runningSeconds, setRunningSeconds] = useState(0);

  useEffect(() => {
    if (run.status !== "running" || !run.startedAt) {
      setRunningSeconds(0);
      return;
    }

    const updateElapsed = () =>
      setRunningSeconds((Date.now() - run.startedAt!) / 1_000);
    updateElapsed();
    const timer = window.setInterval(updateElapsed, 100);
    return () => window.clearInterval(timer);
  }, [run.startedAt, run.status]);

  async function copyAnswer() {
    if (!run.answer) return;
    await navigator.clipboard.writeText(run.answer);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1_500);
  }

  const responseTime =
    run.status === "running" ? runningSeconds : run.responseTimeSeconds;
  const isRunning = run.status === "running";
  const isRunnable = model.enabled && model.available;

  return (
    <article
      className={`admin-card model-result-card ${run.status}`}
      aria-busy={isRunning}
    >
      <div className="model-card-header">
        <div>
          <span className="model-source-line">
            {model.family}
            <em className={`provider-badge ${model.isMock ? "mock" : "real"}`}>
              {model.isMock ? "Mock" : model.provider}
            </em>
          </span>
          <h4>{model.label}</h4>
        </div>
        <span className={`model-status ${run.status}`}>
          <StatusIcon status={run.status} />
          {STATUS_LABELS[run.status]}
        </span>
      </div>

      <div className="model-training-summary">
        <span>{model.trainingStage}</span>
        <p>{model.description}</p>
      </div>

      <dl className="model-metrics">
        <div>
          <dt>{isRunning ? "Elapsed" : "응답 시간"}</dt>
          <dd>
            {responseTime === undefined
              ? "—"
              : `${responseTime.toFixed(2)} sec`}
          </dd>
        </div>
        <div>
          <dt>Input / Output</dt>
          <dd>
            {run.inputTokens == null || run.outputTokens == null
              ? "계산 안 됨"
              : `${run.inputTokens} / ${run.outputTokens}`}
          </dd>
        </div>
        <div>
          <dt>총 Token</dt>
          <dd>{run.totalTokens ?? "계산 안 됨"}</dd>
        </div>
      </dl>

      <div className={`model-response ${run.status}`} aria-live="polite">
        <strong>답변</strong>
        {run.status === "idle" && !isRunnable && (
          <p className="model-error">
            {model.availabilityMessage ?? "현재 실행할 수 없는 모델입니다."}
          </p>
        )}
        {run.status === "idle" && isRunnable && (
          <p>아직 실행하지 않았습니다. 개별 실행할 수 있습니다.</p>
        )}
        {run.status === "running" && (
          <p>
            <LoaderCircle className="spin" size={15} /> 응답 생성 중...
          </p>
        )}
        {run.status === "success" && (
          <>
            <p className="model-answer">{run.answer}</p>
            <button className="copy-button" type="button" onClick={copyAnswer}>
              {copied ? <Check size={15} /> : <Clipboard size={15} />}
              {copied ? "복사됨" : "답변 복사"}
            </button>
          </>
        )}
        {run.status === "error" && (
          <p className="model-error" role="alert">
            {run.error}
          </p>
        )}
        {run.status === "cancelled" && (
          <p className="model-cancelled">{run.error}</p>
        )}
      </div>

      {isRunning ? (
        <button
          className="admin-secondary-button model-run-button cancel"
          type="button"
          onClick={onCancel}
          aria-label={`${model.label} 실행 취소`}
        >
          <Ban size={16} /> 실행 취소
        </button>
      ) : (
        <button
          className="admin-primary-button model-run-button"
          type="button"
          onClick={onRun}
          disabled={!isRunnable}
          aria-label={`${model.label} ${run.status === "idle" ? "실행" : "다시 실행"}`}
        >
          {run.status === "idle" ? <Play size={16} /> : <RotateCcw size={16} />}
          {run.status === "idle" ? "모델 실행" : "다시 실행"}
        </button>
      )}
    </article>
  );
}
