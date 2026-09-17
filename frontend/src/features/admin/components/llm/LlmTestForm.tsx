import { useEffect, useRef, useState } from "react";
import { FileText, LoaderCircle, RotateCcw, X } from "lucide-react";
import {
  describeFileMerge,
  mergeSelectedFiles,
  MESSAGE_UPLOAD_ACCEPT,
  MESSAGE_UPLOAD_EXTENSIONS,
} from "../../../../utils/uploadFiles";

type Props = {
  prompt: string;
  files: File[];
  isRunningAll: boolean;
  hasRunningModels: boolean;
  isLoadingModels: boolean;
  hasRunnableModels: boolean;
  error: string;
  onPromptChange: (value: string) => void;
  onFilesChange: (files: File[]) => void;
  onRunAll: () => void;
  onReset: () => void;
};

export function LlmTestForm(props: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [fileError, setFileError] = useState("");

  useEffect(() => {
    if (props.files.length === 0 && fileRef.current) fileRef.current.value = "";
  }, [props.files.length]);

  function selectFiles(selected: FileList | null) {
    if (!selected?.length) return;
    const merged = mergeSelectedFiles(
      props.files,
      Array.from(selected),
      MESSAGE_UPLOAD_EXTENSIONS,
    );
    props.onFilesChange(merged.files);
    setFileError(describeFileMerge(merged, "PDF, PNG, JPG, DOCX, PPTX, TXT, CSV"));
    if (fileRef.current) fileRef.current.value = "";
  }

  function removeFile(index: number) {
    props.onFilesChange(props.files.filter((_, currentIndex) => currentIndex !== index));
    setFileError("");
  }

  return (
    <div className="admin-card llm-form-card">
      <label className="admin-field">
        <span>공통 질문 / Prompt</span>
        <textarea
          value={props.prompt}
          onChange={(event) => props.onPromptChange(event.target.value)}
          placeholder="예: 이 의료 문서의 핵심 내용을 근거 중심으로 요약해 주세요."
          rows={4}
        />
      </label>

      <div className="llm-reference-field">
        <div className="llm-attachment-row">
          <button
            className="admin-secondary-button"
            type="button"
            onClick={() => fileRef.current?.click()}
          >
            <FileText size={16} /> RAG 참고 파일 선택
          </button>
          <input
            ref={fileRef}
            className="admin-visually-hidden"
            type="file"
            multiple
            accept={MESSAGE_UPLOAD_ACCEPT}
            aria-label="LLM 비교 RAG 참고 파일 선택"
            onChange={(event) => selectFiles(event.target.files)}
          />
          {props.files.map((file, index) => (
            <span className="file-chip" key={`${file.name}-${file.size}-${file.lastModified}`}>
              {file.name}
              <button
                type="button"
                aria-label={`${file.name} 제거`}
                onClick={() => removeFile(index)}
              >
                <X size={13} />
              </button>
            </span>
          ))}
        </div>
        <small>
          최대 5개를 선택할 수 있습니다. 파일 내용은 아직 업로드되지 않으며,
          모든 모델에는 선택한 파일명 조건만 동일하게 전달됩니다.
        </small>
        {fileError && <p className="admin-error" role="alert">{fileError}</p>}
      </div>

      {props.error && (
        <p className="admin-error" role="alert">
          {props.error}
        </p>
      )}

      <div className="llm-form-actions">
        <button
          className="admin-primary-button llm-run-all-button"
          type="button"
          onClick={props.onRunAll}
          disabled={
            props.hasRunningModels ||
            props.isRunningAll ||
            props.isLoadingModels ||
            !props.hasRunnableModels
          }
          aria-busy={props.isRunningAll}
        >
          {props.isRunningAll ? (
            <>
              <LoaderCircle className="spin" size={17} /> 전체 모델 실행 중...
            </>
          ) : props.isLoadingModels ? (
            "모델 목록 확인 중..."
          ) : props.hasRunningModels ? (
            "개별 모델 실행 중..."
          ) : !props.hasRunnableModels ? (
            "실행 가능한 모델 없음"
          ) : (
            "전체 모델 비교 시작"
          )}
        </button>
        <button
          className="admin-secondary-button llm-reset-button"
          type="button"
          onClick={props.onReset}
        >
          <RotateCcw size={16} /> 입력 및 결과 초기화
        </button>
      </div>
    </div>
  );
}
