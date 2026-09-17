import { useRef, useState } from "react";
import {
  CheckCircle2,
  Database,
  FileText,
  Loader2,
  Play,
  RefreshCw,
  RotateCcw,
  Type,
  Upload,
} from "lucide-react";
import {
  parseGroundTruth,
  runAnswerEvaluation,
  runRetrievalEvaluation,
} from "../../../../api/evaluations";
import type {
  AnswerEvaluationResponse,
  GroundTruthParseResponse,
  RetrievalEvalResult,
} from "../../../../api/evaluations";
import { ApiError } from "../../../../services/apiClient";

type InputMode = "file" | "text";
type RetrievalStatus = "idle" | "loading" | "success" | "error";

function errorMessage(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback;
}

function percent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

export function EvaluationPanel() {
  const [inputMode, setInputMode] = useState<InputMode>("file");
  const [groundTruthFile, setGroundTruthFile] = useState<File | null>(null);
  const [groundTruthText, setGroundTruthText] = useState("");
  const [dataset, setDataset] = useState<GroundTruthParseResponse | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [answerResult, setAnswerResult] = useState<AnswerEvaluationResponse | null>(null);
  const [isParsing, setIsParsing] = useState(false);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [answerError, setAnswerError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [retrievalStatus, setRetrievalStatus] = useState<RetrievalStatus>("idle");
  const [retrievalResult, setRetrievalResult] = useState<RetrievalEvalResult | null>(null);
  const [retrievalError, setRetrievalError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const canParse = inputMode === "file" ? Boolean(groundTruthFile) : Boolean(groundTruthText.trim());
  const completedAnswerCount = dataset
    ? dataset.cases.filter((item) => answers[item.id]?.trim()).length
    : 0;
  const canEvaluate = Boolean(dataset) && completedAnswerCount === dataset?.cases.length;

  function changeInputMode(mode: InputMode) {
    setInputMode(mode);
    setAnswerError(null);
  }

  function selectGroundTruthFile(file: File | null) {
    setAnswerError(null);
    setDataset(null);
    setAnswers({});
    setAnswerResult(null);

    if (file && file.size > 2 * 1024 * 1024) {
      setGroundTruthFile(null);
      setAnswerError("정답 데이터 파일은 2MB 이하여야 합니다.");
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }
    setGroundTruthFile(file);
  }

  async function loadGroundTruth() {
    if (!canParse) return;

    setIsParsing(true);
    setAnswerError(null);
    setAnswerResult(null);
    try {
      const parsed = await parseGroundTruth(
        inputMode === "file" ? { file: groundTruthFile ?? undefined } : { text: groundTruthText },
      );
      setDataset(parsed);
      setAnswers(Object.fromEntries(parsed.cases.map((item) => [item.id, ""])));
    } catch (error) {
      setDataset(null);
      setAnswers({});
      setAnswerError(errorMessage(error, "정답 데이터를 불러오지 못했어요."));
    } finally {
      setIsParsing(false);
    }
  }

  function updateAnswer(id: string, value: string) {
    setAnswers((current) => ({ ...current, [id]: value }));
    setAnswerResult(null);
    setAnswerError(null);
  }

  function resetAnswerEvaluation() {
    setGroundTruthFile(null);
    setGroundTruthText("");
    setDataset(null);
    setAnswers({});
    setAnswerResult(null);
    setAnswerError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function evaluateAnswers() {
    if (!dataset || !canEvaluate) return;

    setIsEvaluating(true);
    setAnswerError(null);
    try {
      const result = await runAnswerEvaluation(
        dataset.cases.map((item) => ({
          ...item,
          predictedAnswer: answers[item.id].trim(),
        })),
      );
      setAnswerResult(result);
    } catch (error) {
      setAnswerResult(null);
      setAnswerError(errorMessage(error, "답변 평가에 실패했어요."));
    } finally {
      setIsEvaluating(false);
    }
  }

  async function runRetrievalEval() {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setRetrievalStatus("loading");
    setRetrievalError(null);
    try {
      const data = await runRetrievalEvaluation(controller.signal);
      setRetrievalResult(data);
      setRetrievalStatus("success");
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setRetrievalError(errorMessage(error, "평가 실행에 실패했어요."));
      setRetrievalStatus("error");
    }
  }

  const kValues = retrievalResult
    ? Object.keys(retrievalResult.recallAtK).sort((a, b) => Number(a) - Number(b))
    : [];

  return (
    <section className="admin-workspace" aria-labelledby="eval-panel-title">
      <div className="admin-section-heading">
        <div>
          <span className="admin-eyebrow">PERFORMANCE EVALUATION</span>
          <h2 id="eval-panel-title">성능 지표</h2>
          <p>정답 기반 답변 품질과 RAG 검색 정확도를 각각 평가할 수 있습니다.</p>
        </div>
      </div>

      <div className="admin-evaluation-stack">
        <article className="admin-card answer-evaluation-card">
          <header className="admin-card-header answer-evaluation-header">
            <div>
              <span>GROUND TRUTH EVAL</span>
              <strong>정답 데이터 기반 답변 평가</strong>
            </div>
            {(dataset || groundTruthFile || groundTruthText) && (
              <button
                type="button"
                className="admin-secondary-button"
                onClick={resetAnswerEvaluation}
                disabled={isParsing || isEvaluating}
              >
                <RotateCcw size={15} /> 초기화
              </button>
            )}
          </header>

          <div className="answer-evaluation-body">
            <p className="answer-evaluation-description">
              JSON, JSONL, CSV, TXT 파일을 올리거나 정답 데이터를 직접 입력하세요. 불러온 각
              항목에 모델 답변을 붙여 넣으면 Exact Match, Token F1, 문자 유사도를 계산합니다.
            </p>

            <div className="answer-input-tabs" role="tablist" aria-label="정답 데이터 입력 방법">
              <button
                type="button"
                role="tab"
                aria-selected={inputMode === "file"}
                className={inputMode === "file" ? "active" : ""}
                onClick={() => changeInputMode("file")}
              >
                <Upload size={15} /> 파일 업로드
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={inputMode === "text"}
                className={inputMode === "text" ? "active" : ""}
                onClick={() => changeInputMode("text")}
              >
                <Type size={15} /> 텍스트 입력
              </button>
            </div>

            {inputMode === "file" ? (
              <label className="answer-file-select">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".json,.jsonl,.csv,.txt"
                  onChange={(event) => selectGroundTruthFile(event.target.files?.[0] ?? null)}
                  hidden
                />
                <FileText size={30} />
                <strong>{groundTruthFile?.name ?? "정답 데이터 파일 선택"}</strong>
                <span>
                  {groundTruthFile
                    ? `${(groundTruthFile.size / 1024).toFixed(1)} KB`
                    : "JSON · JSONL · CSV · TXT / 최대 2MB · 최대 200개"}
                </span>
              </label>
            ) : (
              <label className="admin-field answer-text-input">
                정답 데이터
                <textarea
                  value={groundTruthText}
                  onChange={(event) => {
                    setGroundTruthText(event.target.value);
                    setDataset(null);
                    setAnswers({});
                    setAnswerResult(null);
                    setAnswerError(null);
                  }}
                  placeholder={"질문: 대한민국의 수도는?\n정답: 서울\n---\n질문: 1+1은?\n정답: 2"}
                />
                <small>
                  <code>질문: ... / 정답: ...</code> 블록, 한 줄의 <code>질문|정답</code>, JSON
                  형식을 지원합니다. 구분자가 없는 텍스트는 단일 정답으로 처리합니다.
                </small>
              </label>
            )}

            <div className="answer-format-guide">
              <span>파일 열 예시</span>
              <code>question,expected_answer</code>
              <code>질문,정답</code>
            </div>

            <button
              type="button"
              className="admin-primary-button answer-load-button"
              onClick={() => void loadGroundTruth()}
              disabled={!canParse || isParsing || isEvaluating}
            >
              {isParsing ? (
                <>
                  <Loader2 className="spin" size={16} /> 정답 데이터 확인 중...
                </>
              ) : (
                <>
                  <Database size={16} /> 정답 데이터 불러오기
                </>
              )}
            </button>

            {answerError && (
              <p className="admin-error" role="alert">
                {answerError}
              </p>
            )}

            {dataset && (
              <div className="answer-dataset">
                <div className="answer-dataset-summary">
                  <span>
                    <CheckCircle2 size={16} /> <strong>{dataset.sourceName}</strong>
                  </span>
                  <span>{dataset.cases.length}개 항목</span>
                </div>

                <div className="answer-case-list">
                  {dataset.cases.map((item, index) => (
                    <section className="answer-case" key={item.id}>
                      <span className="answer-case-number">{index + 1}</span>
                      <div className="answer-case-content">
                        <div className="answer-reference-grid">
                          <div>
                            <span>질문</span>
                            <p>{item.question}</p>
                          </div>
                          <div>
                            <span>정답</span>
                            <p>{item.expectedAnswer}</p>
                          </div>
                        </div>
                        <label className="admin-field">
                          모델 답변
                          <textarea
                            value={answers[item.id] ?? ""}
                            onChange={(event) => updateAnswer(item.id, event.target.value)}
                            placeholder="이 질문에 대한 모델의 실제 답변을 붙여 넣으세요."
                          />
                        </label>
                      </div>
                    </section>
                  ))}
                </div>

                <div className="answer-run-row">
                  <span>
                    모델 답변 입력 {completedAnswerCount} / {dataset.cases.length}
                  </span>
                  <button
                    type="button"
                    className="admin-primary-button"
                    onClick={() => void evaluateAnswers()}
                    disabled={!canEvaluate || isEvaluating}
                  >
                    {isEvaluating ? (
                      <>
                        <Loader2 className="spin" size={16} /> 평가 중...
                      </>
                    ) : (
                      <>
                        <Play size={16} /> 답변 평가 실행
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}

            {answerResult && (
              <div className="answer-results" aria-live="polite">
                <div className="answer-metric-grid">
                  <div>
                    <span>Exact Match</span>
                    <strong>{percent(answerResult.exactMatch)}</strong>
                    <small>정규화 후 완전 일치</small>
                  </div>
                  <div>
                    <span>Token F1</span>
                    <strong>{percent(answerResult.tokenF1)}</strong>
                    <small>단어·숫자 겹침</small>
                  </div>
                  <div>
                    <span>문자 유사도</span>
                    <strong>{percent(answerResult.characterSimilarity)}</strong>
                    <small>문자열 순서 유사도</small>
                  </div>
                </div>

                <div className="answer-result-list">
                  {answerResult.results.map((item, index) => (
                    <div className="answer-result-row" key={item.id}>
                      <strong>#{index + 1}</strong>
                      <span>EM {percent(item.exactMatch)}</span>
                      <span>F1 {percent(item.tokenF1)}</span>
                      <span>문자 {percent(item.characterSimilarity)}</span>
                    </div>
                  ))}
                </div>

                <p className="llm-provider-notice">
                  이 평가는 문자열 기반 자동 지표입니다. 의학적 사실성, 출처의 신뢰도, 의미상
                  동등성은 별도 검토가 필요합니다.
                </p>
              </div>
            )}
          </div>
        </article>

        <article className="admin-card retrieval-evaluation-card">
          <header className="admin-card-header retrieval-evaluation-header">
            <div>
              <span>RAG RETRIEVAL EVAL</span>
              <strong>검색 정확도 (Recall@k / MRR)</strong>
            </div>
          </header>
          <div className="retrieval-evaluation-body">
            <p>
              미리 준비된 평가 데이터셋(<code>scripts/eval_data</code>)에 대해 검색 정확도를
              계산합니다. 현재는 해싱 임베딩과 dense 검색 단독 기준입니다.
            </p>
            <p className="llm-provider-notice">
              corpus와 쿼리 임베딩을 매번 새로 계산합니다. 실제 임베딩 모델로 교체하면
              데이터셋 크기에 따라 몇 분 정도 걸릴 수 있습니다.
            </p>
            <button
              type="button"
              className="admin-primary-button"
              onClick={() => void runRetrievalEval()}
              disabled={retrievalStatus === "loading"}
            >
              {retrievalStatus === "loading" ? (
                <>
                  <Loader2 className="spin" size={16} /> 평가 실행 중...
                </>
              ) : (
                <>
                  <RefreshCw size={16} /> 검색 평가 실행
                </>
              )}
            </button>

            {retrievalStatus === "error" && (
              <p className="admin-error" role="alert">
                {retrievalError}
              </p>
            )}

            {retrievalResult && (
              <div className="retrieval-result">
                <div className="admin-card-header">
                  <span>{retrievalResult.datasetName}</span>
                  <span className="mock-badge">쿼리 {retrievalResult.numQueries}개</span>
                </div>
                <table className="admin-eval-table">
                  <thead>
                    <tr>
                      {kValues.map((k) => (
                        <th key={k}>Recall@{k}</th>
                      ))}
                      <th>MRR</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      {kValues.map((k) => (
                        <td key={k}>{percent(retrievalResult.recallAtK[k])}</td>
                      ))}
                      <td>{retrievalResult.mrr.toFixed(3)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </article>
      </div>
    </section>
  );
}
