import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { MessageInput } from '../../components/Chat/MessageInput';
import { createConversation } from '../../api/conversations';

type ConsultationPageProps = {
  greeting?: string;
};

export function ConsultationPage({ greeting = '무엇을 도와드릴까요?' }: ConsultationPageProps) {
  const navigate = useNavigate();
  const [starting, setStarting] = useState(false);

  async function handleSend(content: string, files: File[]) {
    if (starting) return;
    setStarting(true);
    try {
      const conversation = await createConversation();
      navigate(`/chat/${conversation.id}`, { state: { pendingMessage: content, pendingFiles: files } });
    } finally {
      setStarting(false);
    }
  }

  return (
    <div className="flex h-full w-full items-center justify-center px-6">
      {/* 대화 시작 전(홈)에는 인사말+입력창을 한 덩어리로 화면 정중앙에 둔다.
          대화가 시작되면 ChatPage로 전환되고, 거기서는 입력창이 하단에 고정된다. */}
      <div className="flex w-full max-w-3xl flex-col items-center gap-4">
        <div className="rounded-2xl bg-neutral-100 px-6 py-4 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-200">
          {greeting}
        </div>
        <div className="w-full">
          <MessageInput onSend={handleSend} disabled={starting} placeholder="메시지를 입력하세요" />
        </div>
        {/* 게스트 세션 발급 + 대화 생성이 겹치는 첫 전송은 네트워크 왕복이 두 번이라
            눈에 띄게 오래 걸릴 수 있다 — 아무 표시가 없으면 멈춘 것처럼 보이니 명시. */}
        {starting && (
          <p className="text-xs text-neutral-400 dark:text-neutral-500">대화를 준비하고 있어요...</p>
        )}
      </div>
    </div>
  );
}
