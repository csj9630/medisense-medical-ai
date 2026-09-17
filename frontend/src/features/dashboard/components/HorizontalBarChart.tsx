import { useState } from 'react';
import { ChartTooltip, type TooltipState } from './ChartTooltip';
import { hBarPath } from './hBarPath';

export type BarItem = { label: string; value: number; tooltipValue?: string };

/** 단일 지표를 카테고리별로 비교하는 가로 막대 — 순위가 아니라 그냥 카테고리
 * 비교라서 막대는 전부 같은 색(slot 1)을 쓴다(값 크다고 진하게 칠하는 건
 * "명목 카테고리에 값 램프" 안티패턴). 막대 두께 22px(마크 스펙 24px 이하),
 * 데이터 끝만 둥글게. */
export function HorizontalBarChart({ items, valueLabel = '' }: { items: BarItem[]; valueLabel?: string }) {
  const [tooltip, setTooltip] = useState<TooltipState>(null);

  if (items.length === 0) {
    return <div className="chart-empty">아직 쌓인 데이터가 없어요.</div>;
  }

  const W = 420;
  const padL = 96;
  const padR = 46;
  const rowH = 34;
  const barH = 22;
  const H = items.length * rowH + 8;
  const max = Math.max(1, ...items.map((it) => it.value));
  const plotW = W - padL - padR;

  return (
    <>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img" aria-label="항목별 비교 막대 차트">
        {items.map((item, i) => {
          const rowTop = 4 + i * rowH;
          const y = rowTop + (rowH - barH) / 2;
          const barW = (item.value / max) * plotW;
          const display = item.tooltipValue ?? `${item.value}${valueLabel}`;
          return (
            <g
              key={item.label}
              className="dashboard-hit"
              tabIndex={0}
              onPointerMove={(e) => setTooltip({ x: e.clientX, y: e.clientY, label: item.label, value: display })}
              onPointerLeave={() => setTooltip(null)}
              onFocus={(e) => {
                const r = e.currentTarget.getBoundingClientRect();
                setTooltip({ x: r.left, y: r.top, label: item.label, value: display });
              }}
              onBlur={() => setTooltip(null)}
            >
              <text x={padL - 10} y={y + barH / 2 + 4} textAnchor="end" fontSize={12.5} fill="var(--admin-text)">
                {item.label}
              </text>
              <path d={hBarPath(padL, y, plotW, barH, 4, false, true)} fill="var(--chart-track)" />
              <path d={hBarPath(padL, y, Math.max(barW, 2), barH, 4, false, true)} fill="var(--series-1)" />
              <text
                x={padL + barW + 8}
                y={y + barH / 2 + 4}
                fontSize={12}
                fontWeight={700}
                fill="var(--admin-text)"
              >
                {display}
              </text>
              <rect x={padL} y={rowTop} width={plotW} height={rowH} fill="transparent" />
            </g>
          );
        })}
      </svg>
      <ChartTooltip state={tooltip} />
    </>
  );
}
