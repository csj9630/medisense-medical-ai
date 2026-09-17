import { useRef, type KeyboardEvent } from "react";
import { BrainCircuit, LineChart, ScanText } from "lucide-react";
import type { AdminTab } from "../types/common";

const TABS: { id: AdminTab; label: string }[] = [
  { id: "ocr", label: "RAG 등록" },
  { id: "llm", label: "LLM" },
  { id: "eval", label: "성능 지표" },
];

export function AdminTabs({
  value,
  onChange,
}: {
  value: AdminTab;
  onChange: (tab: AdminTab) => void;
}) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    let next = index;
    if (event.key === "ArrowRight") next = (index + 1) % TABS.length;
    if (event.key === "ArrowLeft")
      next = (index - 1 + TABS.length) % TABS.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = TABS.length - 1;
    onChange(TABS[next].id);
    refs.current[next]?.focus();
  }
  return (
    <div className="admin-tabs" role="tablist" aria-label="AI 관리 도구">
      {TABS.map((tab, index) => (
        <button
          key={tab.id}
          ref={(node) => {
            refs.current[index] = node;
          }}
          id={`${tab.id}-tab`}
          type="button"
          role="tab"
          aria-selected={value === tab.id}
          aria-controls={`${tab.id}-tabpanel`}
          tabIndex={value === tab.id ? 0 : -1}
          className={value === tab.id ? "active" : ""}
          onClick={() => onChange(tab.id)}
          onKeyDown={(event) => onKeyDown(event, index)}
        >
          {tab.id === "ocr" ? (
            <ScanText size={17} />
          ) : tab.id === "llm" ? (
            <BrainCircuit size={17} />
          ) : (
            <LineChart size={17} />
          )}
          {tab.label}
        </button>
      ))}
    </div>
  );
}
