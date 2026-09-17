export interface Conversation {
  id: string;
  title: string;
  isTitleCustom: boolean;
  category?: string;
  updatedAt: string;
}

export interface MessageAttachment {
  name: string;
  type?: string;
  size?: number;
  /**
   * 방금 이 브라우저에서 첨부한 파일이면 URL.createObjectURL로 만든 blob: URL이 들어있어
   * 원본을 바로 미리볼 수 있다. 서버에서 불러온(새로고침/이전 대화) 첨부는 아직 실제
   * 파일이 저장되지 않아(Object Storage 연동 전) url이 없다 — DocumentPreviewPanel이
   * 이 경우 "원본 저장 전" 안내를 보여준다.
   */
  url?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: string;
  attachments?: MessageAttachment[];
}
