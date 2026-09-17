export type TooltipState = { x: number; y: number; label: string; value: string } | null;

/** 라인/막대 차트가 공용으로 쓰는 최소 툴팁 — 각 차트가 로컬 state로 들고 있다가
 * pointermove/leave에서 값만 바꿔 넘긴다. */
export function ChartTooltip({ state }: { state: TooltipState }) {
  if (!state) return null;
  return (
    <div
      className="dashboard-tooltip"
      style={{ opacity: 1, transform: `translate(${state.x + 14}px, ${state.y - 14}px)` }}
    >
      <span className="tt-label">{state.label}</span>
      <span className="tt-val">{state.value}</span>
    </div>
  );
}
