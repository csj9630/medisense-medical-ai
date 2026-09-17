/** 가로 막대용 rect 경로 — "데이터 끝(data-end)만 둥글게, 기준선(baseline)은
 * 각지게" 마크 스펙을 지키기 위해 좌/우 모서리를 독립적으로 둥글릴 수 있는
 * path를 만든다. (dataviz 스킬 마크 스펙 참고) */
export function hBarPath(
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
  roundLeft: boolean,
  roundRight: boolean,
): string {
  const rl = roundLeft ? Math.min(r, h / 2, w / 2) : 0;
  const rr = roundRight ? Math.min(r, h / 2, w / 2) : 0;
  return [
    `M${x + rl},${y}`,
    `H${x + w - rr}`,
    rr ? `A${rr},${rr} 0 0 1 ${x + w},${y + rr}` : '',
    `V${y + h - rr}`,
    rr ? `A${rr},${rr} 0 0 1 ${x + w - rr},${y + h}` : '',
    `H${x + rl}`,
    rl ? `A${rl},${rl} 0 0 1 ${x},${y + h - rl}` : '',
    `V${y + rl}`,
    rl ? `A${rl},${rl} 0 0 1 ${x + rl},${y}` : '',
    'Z',
  ]
    .filter(Boolean)
    .join(' ');
}
