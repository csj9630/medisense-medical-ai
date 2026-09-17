import { ExternalLink, Eye, Globe2 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

function previewableUrl(value: string): string | null {
  try {
    const parsed = new URL(value.trim());
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.href : null;
  } catch {
    return null;
  }
}

export function OcrWebUrlInput({
  value,
  disabled,
  onChange,
}: {
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  const [previewUrl, setPreviewUrl] = useState('');
  const [previewError, setPreviewError] = useState('');
  const validUrl = useMemo(() => previewableUrl(value), [value]);

  useEffect(() => {
    setPreviewUrl('');
    setPreviewError('');
  }, [value]);

  function showPreview() {
    if (!validUrl) {
      setPreviewError('http 또는 https로 시작하는 올바른 URL을 입력해 주세요.');
      return;
    }
    setPreviewError('');
    setPreviewUrl(validUrl);
  }

  return (
    <div className="ocr-url-source">
      <label className="admin-field" htmlFor="ocr-web-url">
        웹페이지 주소
        <div className="ocr-url-input-row">
          <Globe2 size={17} aria-hidden="true" />
          <input
            id="ocr-web-url"
            type="url"
            inputMode="url"
            maxLength={500}
            placeholder="https://example.com/article"
            value={value}
            disabled={disabled}
            onChange={(event) => onChange(event.target.value)}
          />
        </div>
      </label>
      <p className="ocr-url-help">
        로그인 없이 공개된 HTML 페이지의 본문과 내부 이미지를 수집합니다.
      </p>
      <div className="ocr-url-actions">
        <button
          className="admin-secondary-button"
          type="button"
          disabled={disabled || !value.trim()}
          onClick={showPreview}
        >
          <Eye size={15} /> 미리보기
        </button>
        {validUrl && (
          <a href={validUrl} target="_blank" rel="noopener noreferrer">
            새 창에서 확인 <ExternalLink size={13} />
          </a>
        )}
      </div>
      {previewError && <p className="admin-error" role="alert">{previewError}</p>}
      {previewUrl && (
        <section className="ocr-file-preview" aria-label="웹페이지 미리보기">
          <div className="ocr-preview-header">
            <strong>웹페이지 미리보기</strong>
            <span>사이트 정책에 따라 표시되지 않을 수 있습니다.</span>
          </div>
          <iframe
            className="ocr-web-preview"
            title="입력한 웹페이지 미리보기"
            src={previewUrl}
            sandbox=""
            referrerPolicy="no-referrer"
          />
        </section>
      )}
    </div>
  );
}
