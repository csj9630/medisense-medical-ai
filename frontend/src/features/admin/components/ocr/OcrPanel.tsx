import { CheckCircle2, Database, RefreshCw } from "lucide-react";
import { useOcrTest } from "../../hooks/useOcrTest";
import { OcrChunkSettings } from "./OcrChunkSettings";
import { OcrDropzone } from "./OcrDropzone";
import { OcrFilePreview } from "./OcrFilePreview";
import { OcrResultSummary } from "./OcrResultSummary";
import { OcrSourceSelector } from "./OcrSourceSelector";
import { OcrWebUrlInput } from "./OcrWebUrlInput";
import { SelectedFile } from "./SelectedFile";

export function OcrPanel() {
  const ocr = useOcrTest();
  const sourceSubject = ocr.sourceType === "url" ? "웹페이지가" : "선택한 문서가";
  const sourceObject = ocr.sourceType === "url" ? "웹페이지를" : "선택한 문서를";

  return (
    <section className="admin-workspace" aria-labelledby="ocr-panel-title">
      <div className="admin-section-heading">
        <div>
          <span className="admin-eyebrow">RAG CONTENT INGESTION</span>
          <h2 id="ocr-panel-title">RAG 자료 추출 및 등록</h2>
          <p>
            문서 파일 또는 공개 웹페이지에서 텍스트와 이미지 내용을 추출하고,
            RAG 지식으로 저장하기 전에 추출 품질과 예상 chunk 구성을 확인합니다.
          </p>
        </div>
        {/* <span className="mock-badge">프론트엔드 Mock</span> */}
      </div>
      <div className="ocr-layout">
        <div className="admin-card ocr-input-card">
          <OcrSourceSelector
            value={ocr.sourceType}
            disabled={ocr.isBusy}
            onChange={ocr.setSourceType}
          />

          {ocr.sourceType === "file" ? (
            <>
              <OcrDropzone
                disabled={ocr.isBusy}
                onSelect={ocr.selectFiles}
              />
              {ocr.items.length > 0 ? (
                <div className="selected-file-list">
                  {ocr.items.map((item) => (
                    <SelectedFile
                      key={item.id}
                      file={item.file}
                      selected={item.id === ocr.activeItem?.id}
                      status={item.status}
                      progress={item.progress}
                      disabled={ocr.isBusy}
                      onSelect={() => ocr.setActiveId(item.id)}
                      onRemove={() => ocr.removeFile(item.id)}
                    />
                  ))}
                </div>
              ) : (
                <div className="admin-empty-inline">
                  아직 선택한 파일이 없습니다.
                </div>
              )}
            </>
          ) : (
            <OcrWebUrlInput
              value={ocr.url}
              disabled={ocr.isBusy}
              onChange={ocr.setUrl}
            />
          )}

          <OcrChunkSettings
            chunkSize={ocr.chunkSize}
            overlap={ocr.overlap}
            overlapPercent={ocr.overlapPercent}
            disabled={ocr.isBusy}
            onChunkSizeChange={ocr.setChunkSize}
            onOverlapPercentChange={ocr.setOverlapPercent}
          />

          {ocr.sourceType === "file" && ocr.activeItem && (
            <OcrFilePreview file={ocr.activeItem.file} />
          )}
          {(ocr.error || (ocr.sourceType === "file" && ocr.selectionError)) && (
            <p className="admin-error" role="alert">
              {ocr.error || ocr.selectionError}
            </p>
          )}

          <button
            className="admin-primary-button"
            type="button"
            disabled={!ocr.canAnalyze}
            onClick={() => void ocr.analyze()}
          >
            {ocr.isLoading ? (
              <>
                <RefreshCw className="spin" size={17} /> 내용 추출 중...
              </>
            ) : ocr.sourceType === "file" ? (
              `${ocr.items.length}개 문서 내용 추출`
            ) : (
              "웹페이지 내용 추출"
            )}
          </button>

          <section
            className={`ocr-save-zone ${ocr.canSave ? "is-ready" : ""} ${
              ocr.saveStatus === "success" ? "is-saved" : ""
            }`}
            aria-labelledby="ocr-save-title"
          >
            <div className="ocr-save-heading">
              <span className="ocr-save-icon">
                {ocr.saveStatus === "success" ? (
                  <CheckCircle2 size={18} />
                ) : (
                  <Database size={18} />
                )}
              </span>
              <div>
                <strong id="ocr-save-title">청킹 결과 벡터화 및 저장</strong>
                <span>
                  {ocr.saveStatus === "success"
                    ? `${sourceSubject} VectorDB에 저장되었습니다.`
                    : ocr.result
                      ? "버튼을 클릭하면 Chunk를 벡터화한 뒤 VectorDB에 저장합니다."
                      : "내용 추출과 Chunk 생성이 완료되면 저장할 수 있습니다."}
                </span>
              </div>
              {ocr.saveStatus === "success" && (
                <span className="ocr-saved-badge">저장됨</span>
              )}
            </div>

            <p className="ocr-save-warning">
              이 버튼을 클릭하기 전에는 추출 결과가 VectorDB에 저장되지 않습니다.
            </p>

            <button
              className="admin-primary-button ocr-save-button"
              type="button"
              onClick={() => void ocr.save()}
              disabled={!ocr.canSave}
            >
              {ocr.saveStatus === "loading" ? (
                <>
                  <RefreshCw className="spin" size={17} /> 벡터화 및 저장 중...
                </>
              ) : ocr.saveStatus === "success" ? (
                <>
                  <CheckCircle2 size={17} /> VectorDB 저장 완료
                </>
              ) : (
                <>
                  <Database size={17} /> {sourceObject} VectorDB에 저장
                </>
              )}
            </button>

            {ocr.saveMessage && (
              <p
                className={ocr.saveStatus === "error" ? "admin-error" : "admin-success"}
                role="status"
              >
                {ocr.saveMessage}
              </p>
            )}
          </section>
        </div>

        <div
          className="admin-card ocr-result-card"
          aria-live="polite"
          aria-busy={ocr.status === "loading"}
        >
          <OcrResultSummary
            status={ocr.status}
            progress={ocr.progress}
            result={ocr.result}
          />
        </div>
      </div>
    </section>
  );
}
