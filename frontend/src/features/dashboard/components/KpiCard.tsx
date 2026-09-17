/** value가 null이면 "아직 데이터 없음"을 뜻한다 — 0%/0건으로 잘못 보여주지
 * 않고 명시적으로 빈 상태를 표시한다(근거 없는 수치를 만들지 않는다). */
export function KpiCard({ label, value, sub }: { label: string; value: string | number | null; sub?: string }) {
  const isEmpty = value === null;
  return (
    <div className="dashboard-kpi">
      <div className="k-label">{label}</div>
      <div className={`k-value${isEmpty ? ' empty' : ''}`}>{isEmpty ? '데이터 없음' : value}</div>
      {sub && !isEmpty && <div className="k-sub">{sub}</div>}
    </div>
  );
}
