"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { fmt, hourLabel, type TimelinePoint } from "./api";

const SERIES = [
  { key: "collected" as const, label: "Đã gom", color: "var(--series-1)" },
  { key: "published" as const, label: "Đã public", color: "var(--series-2)" },
];

const HEIGHT = 220;
const PAD = { top: 12, right: 72, bottom: 24, left: 36 };

function niceMax(value: number): number {
  if (value <= 4) return 4;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 2.5, 5, 10].find((m) => m * magnitude >= value / 4)! * magnitude;
  return Math.ceil(value / step) * step;
}

/** Collected vs published per hour, last 24h. One shared count axis. */
export function TimelineChart({ points }: { points: TimelinePoint[] }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  const [hover, setHover] = useState<number | null>(null);
  const [asTable, setAsTable] = useState(false);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(280, entry.contentRect.width)));
    observer.observe(el);
    return () => observer.disconnect();
    // Re-attach when switching back from the table view (new element).
  }, [asTable]);

  const { x, y, yMax, ticks } = useMemo(() => {
    const max = niceMax(Math.max(1, ...points.flatMap((p) => [p.collected, p.published])));
    const plotW = width - PAD.left - PAD.right;
    const plotH = HEIGHT - PAD.top - PAD.bottom;
    return {
      x: (i: number) => PAD.left + (points.length > 1 ? (i / (points.length - 1)) * plotW : plotW / 2),
      y: (v: number) => PAD.top + plotH - (v / max) * plotH,
      yMax: max,
      ticks: [0, 0.25, 0.5, 0.75, 1].map((t) => Math.round(t * max)),
    };
  }, [points, width]);

  if (!points.length) return null;
  const last = points.length - 1;
  const path = (key: "collected" | "published") =>
    points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p[key]).toFixed(1)}`).join("");
  const step = points.length > 1 ? x(1) - x(0) : width;

  // Direct labels at the line ends; nudged apart if they'd overlap.
  const endY = SERIES.map((s) => y(points[last][s.key]));
  if (Math.abs(endY[0] - endY[1]) < 14) {
    const mid = (endY[0] + endY[1]) / 2;
    const up = endY[0] <= endY[1] ? 0 : 1;
    endY[up] = mid - 7;
    endY[1 - up] = mid + 7;
  }

  const hovered = hover !== null ? points[hover] : null;
  const tooltipLeft = hover !== null ? Math.min(Math.max(x(hover) - 70, 0), width - 150) : 0;

  return (
    <div className="viz-root">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-4 text-xs text-muted-foreground" aria-label="Chú giải">
          {SERIES.map((s) => (
            <span key={s.key} className="inline-flex items-center gap-1.5">
              <span className="h-0.5 w-4 rounded-full" style={{ background: s.color }} />
              {s.label}
            </span>
          ))}
        </div>
        <button
          type="button"
          onClick={() => setAsTable((v) => !v)}
          className="rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          {asTable ? "Xem biểu đồ" : "Xem dạng bảng"}
        </button>
      </div>

      {asTable ? (
        <div className="max-h-[220px] overflow-auto rounded-lg border border-border">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-muted text-left text-muted-foreground">
              <tr>
                <th className="px-3 py-1.5 font-medium">Giờ</th>
                {SERIES.map((s) => (
                  <th key={s.key} className="px-3 py-1.5 text-right font-medium">
                    {s.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...points].reverse().map((p) => (
                <tr key={p.hour} className="border-t border-border/60">
                  <td className="px-3 py-1 tabular-nums">{hourLabel(p.hour)}</td>
                  <td className="px-3 py-1 text-right tabular-nums">{fmt(p.collected)}</td>
                  <td className="px-3 py-1 text-right tabular-nums">{fmt(p.published)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div ref={wrapRef} className="relative" onMouseLeave={() => setHover(null)}>
          <svg
            width={width}
            height={HEIGHT}
            role="img"
            aria-label={`Số tin đã gom và đã public theo giờ trong 24 giờ qua, tối đa ${yMax}`}
            className="block overflow-visible"
          >
            {ticks.map((t) => (
              <g key={t}>
                <line x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} stroke="var(--viz-grid)" />
                <text
                  x={PAD.left - 8}
                  y={y(t)}
                  dy="0.32em"
                  textAnchor="end"
                  className="fill-muted-foreground text-[0.625rem] tabular-nums"
                >
                  {t}
                </text>
              </g>
            ))}
            {points.map((p, i) =>
              i % 3 === 0 || i === last ? (
                <text
                  key={p.hour}
                  x={x(i)}
                  y={HEIGHT - 6}
                  textAnchor="middle"
                  className="fill-muted-foreground text-[0.625rem] tabular-nums"
                >
                  {hourLabel(p.hour)}
                </text>
              ) : null
            )}

            {hover !== null && (
              <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={HEIGHT - PAD.bottom} stroke="var(--viz-axis)" />
            )}

            {SERIES.map((s) => (
              <path
                key={s.key}
                d={path(s.key)}
                fill="none"
                stroke={s.color}
                strokeWidth={2}
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            ))}

            {hovered &&
              SERIES.map((s) => (
                <circle
                  key={s.key}
                  cx={x(hover!)}
                  cy={y(hovered[s.key])}
                  r={4.5}
                  fill={s.color}
                  stroke="hsl(var(--background))"
                  strokeWidth={2}
                />
              ))}

            {SERIES.map((s, i) => (
              <text
                key={s.key}
                x={x(last) + 8}
                y={endY[i]}
                dy="0.32em"
                className="fill-foreground text-[0.6875rem] font-medium"
              >
                {s.label} {fmt(points[last][s.key])}
              </text>
            ))}

            {/* Hit targets: one full-height column per hour (wider than the marks). */}
            {points.map((p, i) => (
              <rect
                key={p.hour}
                x={x(i) - step / 2}
                y={PAD.top}
                width={step}
                height={HEIGHT - PAD.top - PAD.bottom}
                fill="transparent"
                onMouseEnter={() => setHover(i)}
                onTouchStart={() => setHover(i)}
              />
            ))}
          </svg>

          {hovered && (
            <div
              role="status"
              className="pointer-events-none absolute top-0 w-[150px] rounded-lg border border-border bg-background px-3 py-2 text-xs shadow-md"
              style={{ left: tooltipLeft }}
            >
              <div className="mb-1 font-semibold tabular-nums">
                {hourLabel(hovered.hour)} –{" "}
                {hourLabel(new Date(new Date(hovered.hour).getTime() + 3600_000).toISOString())}
              </div>
              {SERIES.map((s) => (
                <div key={s.key} className="flex items-center justify-between gap-3">
                  <span className="inline-flex items-center gap-1.5 text-muted-foreground">
                    <span className="h-2 w-2 rounded-full" style={{ background: s.color }} />
                    {s.label}
                  </span>
                  <span className="font-semibold tabular-nums">{fmt(hovered[s.key])}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
