import type { Message } from '../api/types';

// 채팅 화면에서는 이 문구를 답변마다 반복하지 않고 경고 배너로 한 번씩 보여준다
// (MessageBubble.tsx 참고) — 그래서 message.content 안에는 더 이상 이 문구가 없다.
// 내보낸 파일은 화면을 벗어나 따로 보관/공유되므로, 파일 상단에 한 번 명시해둔다.
const MEDICAL_DISCLAIMER = '※ 본 답변은 참고용 정보이며 의학적 진단을 대체하지 않습니다. 정확한 진단은 반드시 의료진과 상담하세요.';

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('ko-KR', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function roleLabel(role: Message['role']): string {
  return role === 'user' ? '환자' : 'AI 상담';
}

function attachmentNames(message: Message): string | null {
  if (!message.attachments?.length) return null;
  return message.attachments.map((a) => a.name).join(', ');
}

function slugifyForFilename(text: string): string {
  const cleaned = text.trim().replace(/[\\/:*?"<>|\n]/g, ' ').replace(/\s+/g, ' ').slice(0, 40);
  return cleaned || '채팅내역';
}

export function buildFilenameBase(messages: Message[]): string {
  const firstUserMessage = messages.find((m) => m.role === 'user')?.content ?? '채팅내역';
  const date = new Date().toISOString().slice(0, 10);
  return `${slugifyForFilename(firstUserMessage)}_${date}`;
}

export function buildTranscriptText(title: string, messages: Message[]): string {
  const header = [title, '전체 대화 원문입니다.', MEDICAL_DISCLAIMER, `생성일시: ${new Date().toLocaleString('ko-KR')}`, '='.repeat(40)].join('\n');
  const body = messages
    .map((m) => {
      const attachments = attachmentNames(m);
      const lines = [`[${formatTimestamp(m.createdAt)}] ${roleLabel(m.role)}`, m.content];
      if (attachments) lines.push(`첨부: ${attachments}`);
      return lines.join('\n');
    })
    .join('\n\n');
  return `${header}\n\n${body}\n`;
}

export function buildTranscriptMarkdown(title: string, messages: Message[]): string {
  const body = messages
    .map((m) => {
      const attachments = attachmentNames(m);
      const attachmentLine = attachments ? `\n\n> 첨부: ${attachments}` : '';
      return `**${roleLabel(m.role)}** _(${formatTimestamp(m.createdAt)})_\n\n${m.content}${attachmentLine}`;
    })
    .join('\n\n---\n\n');
  return `# ${title}\n\n> 전체 대화 원문입니다.\n\n> ${MEDICAL_DISCLAIMER}\n\n생성일시: ${new Date().toLocaleString('ko-KR')}\n\n---\n\n${body}\n`;
}

export function downloadTextFile(filename: string, content: string, mime: string): void {
  const blob = new Blob([content], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function buildPrintableHtml(title: string, messages: Message[]): string {
  const body = messages
    .map((m) => {
      const attachments = attachmentNames(m);
      const attachmentHtml = attachments ? `<p class="attachments">첨부: ${escapeHtml(attachments)}</p>` : '';
      return `
        <section class="turn">
          <p class="meta">${escapeHtml(roleLabel(m.role))} · ${escapeHtml(formatTimestamp(m.createdAt))}</p>
          <p class="content">${escapeHtml(m.content).replace(/\n/g, '<br/>')}</p>
          ${attachmentHtml}
        </section>`;
    })
    .join('\n');

  return `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<title>${escapeHtml(title)}</title>
<style>
  body { font-family: -apple-system, "Malgun Gothic", "Apple SD Gothic Neo", sans-serif; color: #1a1a1a; padding: 32px; max-width: 720px; margin: 0 auto; }
  h1 { font-size: 20px; margin-bottom: 4px; }
  .generated { color: #888; font-size: 12px; margin-bottom: 16px; }
  .note { background: #f5f5f5; border-radius: 8px; padding: 8px 12px; font-size: 12px; color: #555; margin-bottom: 16px; }
  .turn { padding: 10px 0; border-bottom: 1px solid #eee; }
  .meta { font-size: 11px; color: #999; margin: 0 0 4px; }
  .content { font-size: 14px; line-height: 1.6; margin: 0; white-space: pre-wrap; }
  .attachments { font-size: 12px; color: #666; margin: 4px 0 0; }
  @media print { body { padding: 0; } }
</style>
</head>
<body>
  <h1>${escapeHtml(title)}</h1>
  <p class="generated">생성일시: ${escapeHtml(new Date().toLocaleString('ko-KR'))}</p>
  <p class="note">전체 대화 원문입니다.</p>
  <p class="note">${escapeHtml(MEDICAL_DISCLAIMER)}</p>
  ${body}
</body>
</html>`;
}

// PDF는 별도 라이브러리(jsPDF 등) 없이 브라우저 인쇄 대화상자를 이용한다.
// 한글 폰트를 임베드해야 하는 라이브러리 방식과 달리, 브라우저가 시스템 폰트로
// 그려주므로 한글이 항상 정상 출력되고("다른 이름으로 저장 > PDF"로 저장) 번들도 가벼워진다.
//
// window.open()이 아니라 숨겨진 iframe을 쓴다 — 새 창을 여는 방식은 브라우저 팝업
// 차단기에 걸려서 "팝업이 차단되어 있어요" 안내만 계속 뜨고 실제로는 저장이 안 되는
// 문제가 있었다. iframe은 팝업으로 취급되지 않아 이 문제를 원천적으로 피한다.
export function openPrintableTranscript(title: string, messages: Message[]): void {
  const iframe = document.createElement('iframe');
  iframe.style.position = 'fixed';
  iframe.style.right = '0';
  iframe.style.bottom = '0';
  iframe.style.width = '0';
  iframe.style.height = '0';
  iframe.style.border = '0';
  iframe.setAttribute('aria-hidden', 'true');
  document.body.appendChild(iframe);

  const cleanup = () => {
    if (iframe.parentNode) iframe.parentNode.removeChild(iframe);
  };

  const doc = iframe.contentDocument;
  if (!doc) {
    cleanup();
    window.alert('인쇄 미리보기를 여는 데 실패했어요. 잠시 후 다시 시도해주세요.');
    return;
  }

  doc.open();
  doc.write(buildPrintableHtml(title, messages));
  doc.close();

  iframe.onload = () => {
    const win = iframe.contentWindow;
    if (!win) {
      cleanup();
      return;
    }
    win.addEventListener('afterprint', cleanup, { once: true });
    win.focus();
    win.print();
    // 일부 브라우저는 afterprint를 안 쏘기도 해서, 넉넉한 시간 뒤 강제로 한 번 더 정리한다.
    setTimeout(cleanup, 5000);
  };
}
