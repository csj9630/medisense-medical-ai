import { useMemo, useState } from 'react';
import { ChartTooltip, type TooltipState } from './ChartTooltip';

type Point = { date: string; count: number };

/** 일별 카운트 라인 차트 — 크로스헤어+툴팁 포함(dataviz 스킬: "라인/영역은 기본
 * 호버 레이어를 갖춘다"). 시리즈 1개라 범례는 안 둔다(제목이 이미 설명함). */
export function TrendLineChart({ data, unit = '건' }: { data: Point[]; unit?: string }) {
  const [tooltip, setTooltip] = useState<TooltipState>(null);
  const W = 560;
  const H = 200;
  const padL = 30;
  const padR = 8;
  const padT = 10;
  const padB = 22;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const { points, maxValue, formatLabel } = useMemo(() => {
    const max = Math.max(1, ...data.map((d) => d.count));
    const niceMax = Math.ceil(max / 5) * 5 || 5;
    const xFor = (i: number) => padL + (data.length > 1 ? (i / (data.length - 1)) * plotW : plotW / 2);
    const yFor = (v: number) => padT + plotH - (v / niceMax) * plotH;
    const pts = data.map((d, i) => ({ x: xFor(i), y: yFor(d.count), ...d }));
    const fmt = (d: string) => d.slice(5).replace('-', '/'); // "2026-08-28" -> "08/28"
    return { points: pts, maxValue: niceMax, formatLabel: fmt };
  }, [data]);

  if (data.length === 0 || data.every((d) => d.count === 0)) {
    return (
      <>
        <div className="chart-empty">아직 쌓인 데이터가 없어요 — 실제 상담이 시작되면 채워집니다.</div>
      </>
    );
  }

  const areaD =
    `M${points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' L')}` +
    ` L${points[points.length - 1].x.toFixed(1)},${(padT + plotH).toFixed(1)}` +
    ` L${points[0].x.toFixed(1)},${(padT + plotH).toFixed(1)} Z`;
  const lineD = `M${points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' L')}`;

  function handleMove(e: React.PointerEvent<SVGRectElement>) {
    const rect = e.currentTarget.ownerSVGElement!.getBoundingClientRect();
    const scaleX = W / rect.width;
    const localX = (e.clientX - rect.left) * scaleX;
    let idx = data.length > 1 ? Math.round(((localX - padL) / plotW) * (data.length - 1)) : 0;
    idx = Math.max(0, Math.min(data.length - 1, idx));
    const p = points[idx];
    setTooltip({ x: e.clientX, y: e.clientY, label: formatLabel(p.date), value: `${p.count}${unit}` });
  }

  return (
    <>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="추이 라인 차트">
        {[0, maxValue / 2, maxValue].map((v) => {
          const y = padT + plotH - (v / maxValue) * plotH;
          return (
            <g key={v}>
              <line x1={padL} x2={W - padR} y1={y} y2={y} stroke="var(--chart-grid)" strokeWidth={1} />
              <text x={padL - 6} y={y + 4} textAnchor="end" fontSize={10.5} fill="var(--admin-muted)">
                {Math.round(v)}
              </text>
            </g>
          );
        })}
        <path d={areaD} fill="var(--series-1-wash)" stroke="none" />
        <path d={lineD} fill="none" stroke="var(--series-1)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
        {points.map(
          (p, i) =>
            (i === 0 || i === points.length - 1 || i % 3 === 0) && (
              <text key={p.date} x={p.x} y={H - 6} textAnchor="middle" fontSize={10} fill="var(--admin-muted)">
                {formatLabel(p.date)}
              </text>
            ),
        )}
        {tooltip && (
          <circle
            cx={points.find((p) => formatLabel(p.date) === tooltip.label)?.x}
            cy={points.find((p) => formatLabel(p.date) === tooltip.label)?.y}
            r={4}
            fill="var(--series-1)"
            stroke="var(--admin-panel)"
            strokeWidth={2}
          />
        )}
        <rect
          x={padL}
          y={padT}
          width={plotW}
          height={plotH}
          fill="transparent"
          onPointerMove={handleMove}
          onPointerLeave={() => setTooltip(null)}
        />
      </svg>
      <ChartTooltip state={tooltip} />
    </>
  );
}
