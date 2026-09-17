import { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { useModelSelect } from './ModelSelectContext';
import { getModelOption } from './modelOptions';

const TIER_LABEL: Record<'recommended' | 'beta', string> = {
  recommended: '추천',
  beta: 'Beta',
};

/** 입력창 하단 우측에 두는 LLM 모델 선택 드롭다운. */
export function ModelSelect() {
  const { modelId, modelOptions, setModelId } = useModelSelect();
  const [open, setOpen] = useState(false);
  const current = getModelOption(modelId, modelOptions);

  return (
    <div className="relative">
      <button
        type="button"
        title="응답 모델 선택"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 rounded-lg px-2 py-1 text-sm text-neutral-700 hover:bg-neutral-100 dark:text-neutral-200 dark:hover:bg-white/10"
      >
        <span className="font-medium">{current.label}</span>
        <span className="text-neutral-400 dark:text-neutral-500">{TIER_LABEL[current.tier]}</span>
        <ChevronDown size={13} className="text-neutral-400 dark:text-neutral-500" />
      </button>

      {open && (
        <>
          {/* 바깥 클릭 시 닫기용 오버레이 */}
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute bottom-full right-0 z-20 mb-1.5 w-52 rounded-xl border border-neutral-200 bg-white p-1.5 shadow-lg dark:border-neutral-700 dark:bg-neutral-800">
            {modelOptions.map((option) => (
              <button
                key={option.id}
                type="button"
                onClick={() => {
                  setModelId(option.id);
                  setOpen(false);
                }}
                className={`flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-sm ${
                  option.id === modelId
                    ? 'bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300'
                    : 'text-neutral-700 hover:bg-neutral-100 dark:text-neutral-200 dark:hover:bg-neutral-700'
                }`}
              >
                <span>{option.label}</span>
                <span
                  className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
                    option.tier === 'recommended'
                      ? 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-200'
                      : 'bg-neutral-100 text-neutral-500 dark:bg-neutral-700 dark:text-neutral-300'
                  }`}
                >
                  {TIER_LABEL[option.tier]}
                </span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
