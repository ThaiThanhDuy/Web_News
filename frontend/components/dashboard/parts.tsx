"use client";

import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, PauseCircle, XCircle } from "lucide-react";

import { cn } from "@/lib/utils";

import {
  ago,
  compact,
  duration,
  fmt,
  QUEUE_LABEL,
  STAGE_LABEL,
  type EngagementSummary,
  type QueueRow,
  type SourceRow,
  type TokenRow,
  type Totals,
  type Summary,
  type TrendRow,
} from "./api";

export function Card({
  title,
  action,
  children,
  className,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-2xl border border-border bg-card p-4 sm:p-5", className)}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

// ------------------------------------------------------------- KPI row

export function StatTiles({ totals }: { totals: Totals }) {
  const tiles: { label: string; value: number; sub?: string; status?: "critical" }[] = [
    { label: "Đã gom", value: totals.collected, sub: `+${fmt(totals.collected_24h)} trong 24 giờ` },
    { label: "Đang xử lý", value: totals.processing, sub: "chờ tải trang / AI" },
    { label: "Đã public", value: totals.published, sub: `+${fmt(totals.published_24h)} trong 24 giờ` },
    { label: "Trùng / ẩn", value: totals.duplicate, sub: "cùng tin với nguồn khác" },
    { label: "Bị lọc", value: totals.filtered, sub: "theo rule" },
    {
      label: "Lỗi",
      value: totals.failed,
      sub: totals.failed ? "cần kiểm tra" : "không có",
      status: totals.failed ? "critical" : undefined,
    },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      {tiles.map((t) => (
        <div key={t.label} className="rounded-2xl border border-border bg-card p-4">
          <div className="text-xs font-medium text-muted-foreground">{t.label}</div>
          <div className="mt-1 text-2xl font-bold tabular-nums tracking-tight">{fmt(t.value)}</div>
          <div className="mt-0.5 flex items-center gap-1 text-[0.6875rem] text-muted-foreground">
            {t.status === "critical" && <XCircle className="h-3 w-3" style={{ color: "var(--status-critical)" }} />}
            {t.sub}
          </div>
        </div>
      ))}
    </div>
  );
}

// ------------------------------------------------------------ meters

function Meter({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="h-2 w-full overflow-hidden rounded-full" style={{ background: "var(--meter-track)" }}>
      <div
        className="h-full rounded-full transition-[width] duration-500 ease-out motion-reduce:transition-none"
        style={{ width: `${pct}%`, background: "var(--meter-fill)", minWidth: value > 0 ? 4 : 0 }}
      />
    </div>
  );
}

/** One row per pipeline status: name, bar (share of all items), count. */
export function StageMeters({ stages }: { stages: { status: string; count: number }[] }) {
  const total = stages.reduce((sum, s) => sum + s.count, 0);
  return (
    <ul className="viz-root space-y-2.5">
      {stages.map((s) => (
        <li key={s.status} className="grid grid-cols-[minmax(0,10rem)_1fr_3rem] items-center gap-3 text-xs">
          <span className="truncate text-muted-foreground">{STAGE_LABEL[s.status] ?? s.status}</span>
          <Meter value={s.count} max={total} />
          <span className="text-right font-semibold tabular-nums">{fmt(s.count)}</span>
        </li>
      ))}
    </ul>
  );
}

export function TokenMeters({ tokens, provider }: { tokens: TokenRow[]; provider: string }) {
  if (provider !== "groq") {
    return <p className="text-xs text-muted-foreground">Đang dùng AI tại chỗ ({provider}) — không giới hạn token.</p>;
  }
  if (!tokens.length) return <p className="text-xs text-muted-foreground">Không đọc được số liệu token (Redis?).</p>;
  return (
    <ul className="viz-root space-y-3">
      {tokens.map((t) => {
        const ratio = t.cap ? t.used / t.cap : 0;
        return (
          <li key={t.model} className="space-y-1.5 text-xs">
            <div className="flex items-center justify-between gap-2">
              <span className="min-w-0 truncate">
                <span className="font-medium">{t.model}</span>
                <span className="text-muted-foreground"> · {t.stages.join(", ")}</span>
              </span>
              <span className="shrink-0 tabular-nums text-muted-foreground">
                <span className="font-semibold text-foreground">{compact(t.used)}</span> / {compact(t.cap)}
              </span>
            </div>
            <Meter value={t.used} max={t.cap} />
            {ratio >= 0.9 && (
              <div className="inline-flex items-center gap-1 text-[0.6875rem] text-muted-foreground">
                <AlertTriangle className="h-3 w-3" style={{ color: "var(--status-warning)" }} />
                {ratio >= 1 ? "Hết hạn mức hôm nay — reset lúc 7:00" : "Sắp hết hạn mức hôm nay"}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

// ------------------------------------------------------------ status

function StatusChip({ kind, children }: { kind: "good" | "warning" | "critical"; children: ReactNode }) {
  const Icon = kind === "good" ? CheckCircle2 : kind === "warning" ? PauseCircle : XCircle;
  return (
    <span className="inline-flex items-center gap-1 whitespace-nowrap text-xs">
      <Icon className="h-3.5 w-3.5" style={{ color: `var(--status-${kind})` }} />
      {children}
    </span>
  );
}

function sourceStatus(s: SourceRow) {
  if (!s.is_active) return <StatusChip kind="warning">Tắt</StatusChip>;
  if (s.paused) return <StatusChip kind="critical">Tạm dừng</StatusChip>;
  if (s.consecutive_failures > 0) return <StatusChip kind="warning">Lỗi {s.consecutive_failures} lần</StatusChip>;
  return <StatusChip kind="good">Hoạt động</StatusChip>;
}

const th = "px-3 py-2 text-left text-[0.6875rem] font-medium uppercase tracking-wide text-muted-foreground";
const td = "px-3 py-2 align-top";

export function SourcesTable({ sources }: { sources: SourceRow[] }) {
  return (
    <div className="viz-root -mx-4 overflow-x-auto sm:-mx-5">
      <table className="w-full min-w-[56rem] text-sm">
        <thead className="border-b border-border">
          <tr>
            <th className={cn(th, "pl-4 sm:pl-5")}>Nguồn</th>
            <th className={th}>Trạng thái</th>
            <th className={cn(th, "text-right")}>Đã gom</th>
            <th className={cn(th, "text-right")}>Đang xử lý</th>
            <th className={cn(th, "text-right")}>Public</th>
            <th className={cn(th, "text-right")}>Trùng</th>
            <th className={cn(th, "text-right")}>Lọc / lỗi</th>
            <th className={th}>Cào gần nhất</th>
            <th className={cn(th, "pr-4 sm:pr-5")}>Lần tới</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((s) => (
            <tr key={s.slug} className="border-b border-border/60 last:border-0">
              <td className={cn(td, "pl-4 font-medium sm:pl-5")}>
                {s.name}
                {s.last_error && (
                  <div
                    className="mt-0.5 max-w-[16rem] truncate text-[0.6875rem] font-normal text-muted-foreground"
                    title={s.last_error}
                  >
                    {s.last_error}
                  </div>
                )}
              </td>
              <td className={td}>{sourceStatus(s)}</td>
              <td className={cn(td, "text-right tabular-nums")}>{fmt(s.collected)}</td>
              <td className={cn(td, "text-right tabular-nums")}>{fmt(s.processing)}</td>
              <td className={cn(td, "text-right font-semibold tabular-nums")}>{fmt(s.published)}</td>
              <td className={cn(td, "text-right tabular-nums")}>{fmt(s.duplicate)}</td>
              <td className={cn(td, "text-right tabular-nums")}>
                {fmt(s.filtered)} / {fmt(s.failed)}
              </td>
              <td className={cn(td, "whitespace-nowrap text-xs text-muted-foreground")}>{ago(s.last_fetch_at)}</td>
              <td className={cn(td, "whitespace-nowrap pr-4 text-xs text-muted-foreground sm:pr-5")}>
                {ago(s.next_run_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function QueuesTable({ queues }: { queues: QueueRow[] }) {
  return (
    <div className="viz-root -mx-4 overflow-x-auto sm:-mx-5">
      <table className="w-full min-w-[40rem] text-sm">
        <thead className="border-b border-border">
          <tr>
            <th className={cn(th, "pl-4 sm:pl-5")}>Queue</th>
            <th className={cn(th, "text-right")}>Chờ chạy</th>
            <th className={cn(th, "text-right")}>Hẹn sau</th>
            <th className={cn(th, "text-right")}>Đang chạy</th>
            <th className={cn(th, "text-right")}>Xong (1 giờ)</th>
            <th className={cn(th, "text-right")}>Dead</th>
            <th className={cn(th, "pr-4 text-right sm:pr-5")}>Chờ lâu nhất</th>
          </tr>
        </thead>
        <tbody>
          {queues.map((q) => (
            <tr key={q.queue} className="border-b border-border/60 last:border-0">
              <td className={cn(td, "pl-4 sm:pl-5")}>
                <div className="font-medium">{QUEUE_LABEL[q.queue] ?? q.queue}</div>
                <div className="font-mono text-[0.6875rem] text-muted-foreground">{q.queue}</div>
              </td>
              <td className={cn(td, "text-right font-semibold tabular-nums")}>{fmt(q.due)}</td>
              <td className={cn(td, "text-right tabular-nums text-muted-foreground")}>{fmt(q.scheduled)}</td>
              <td className={cn(td, "text-right tabular-nums")}>{fmt(q.running)}</td>
              <td className={cn(td, "text-right tabular-nums")}>{fmt(q.done_1h)}</td>
              <td className={cn(td, "text-right tabular-nums")}>
                {q.dead > 0 ? <StatusChip kind="critical">{fmt(q.dead)}</StatusChip> : "0"}
              </td>
              <td className={cn(td, "whitespace-nowrap pr-4 text-right text-xs text-muted-foreground sm:pr-5")}>
                {duration(q.oldest_due_seconds)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ------------------------------------------------------ hot-news analytics

/** Keywords rising vs their own baseline; bar = heat (0..1). */
export function TrendMeters({ trends }: { trends: TrendRow[] }) {
  if (!trends.length) return <p className="text-xs text-muted-foreground">Chưa có keyword nào đang lên.</p>;
  return (
    <ul className="viz-root space-y-2.5">
      {trends.map((t) => (
        <li key={t.keyword} className="space-y-1 text-xs">
          <div className="flex items-baseline justify-between gap-2">
            <span className="truncate font-medium">#{t.keyword}</span>
            <span className="shrink-0 tabular-nums text-muted-foreground">
              {t.recent_24h} tin · {t.sources_24h} nguồn · nền {t.baseline_daily.toFixed(1)}/ngày
            </span>
          </div>
          <Meter value={t.heat} max={1} />
        </li>
      ))}
    </ul>
  );
}

export function SearchMeters({ searches }: { searches: { query: string; count: number }[] }) {
  if (!searches.length) return <p className="text-xs text-muted-foreground">Chưa có lượt tìm kiếm nào.</p>;
  const max = Math.max(...searches.map((s) => s.count));
  return (
    <ul className="viz-root space-y-2.5">
      {searches.map((s) => (
        <li key={s.query} className="grid grid-cols-[minmax(0,8rem)_1fr_2.5rem] items-center gap-3 text-xs">
          <span className="truncate">{s.query}</span>
          <Meter value={s.count} max={max} />
          <span className="text-right font-semibold tabular-nums">{fmt(s.count)}</span>
        </li>
      ))}
    </ul>
  );
}

export function EngagementPanel({ engagement: e }: { engagement: EngagementSummary }) {
  const ctr = e.impressions_24h ? (e.clicks_24h / e.impressions_24h) * 100 : 0;
  const stats = [
    { label: "Lượt hiển thị", value: fmt(e.impressions_24h) },
    { label: "Lượt mở bài", value: fmt(e.clicks_24h) },
    { label: "Tỉ lệ mở", value: `${ctr.toFixed(1)}%` },
    { label: "Bấm hashtag", value: fmt(e.tag_clicks_24h) },
    { label: "Mở thông báo", value: fmt(e.push_opens_24h) },
    { label: "Lượt tìm", value: fmt(e.searches_24h) },
  ];
  return (
    <div className="viz-root space-y-3">
      <div className="grid grid-cols-3 gap-2">
        {stats.map((s) => (
          <div key={s.label}>
            <div className="text-[0.6875rem] text-muted-foreground">{s.label}</div>
            <div className="text-base font-bold tabular-nums">{s.value}</div>
          </div>
        ))}
      </div>
      {e.in_ranking ? (
        <StatusChip kind="good">Đang dùng trong xếp hạng tin hot</StatusChip>
      ) : (
        <StatusChip kind="warning">
          Chưa dùng để xếp hạng: cần ≥ {fmt(e.min_daily_impressions)} lượt hiển thị/ngày ({fmt(e.impressions_24h)})
        </StatusChip>
      )}
      {e.top_clicked.length > 0 && (
        <div>
          <div className="mb-1 text-[0.6875rem] font-medium uppercase tracking-wide text-muted-foreground">
            Được mở nhiều nhất
          </div>
          <ol className="space-y-1 text-xs">
            {e.top_clicked.map((t) => (
              <li key={t.id} className="flex items-baseline justify-between gap-2">
                <a href={t.url} target="_blank" rel="noopener noreferrer" className="truncate hover:text-primary">
                  {t.title}
                </a>
                <span className="shrink-0 tabular-nums text-muted-foreground">
                  {fmt(t.clicks)}/{fmt(t.impressions)}
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

/** Status of the CPU-only topic classifier (self-gated by its accuracy). */
export function LocalClassifierStatus({ status }: { status: Summary["local_classifier"] }) {
  const accuracy = status.keep_drop_accuracy !== undefined ? `${Math.round(status.keep_drop_accuracy * 100)}%` : "—";
  return (
    <div className="viz-root mt-4 border-t border-border pt-3 text-xs">
      <div className="mb-1 font-medium">Phân loại tại chỗ (CPU, không tốn token)</div>
      {status.active ? (
        <StatusChip kind="good">
          Đang dùng · tự quyết {Math.round((status.decided_share ?? 0) * 100)}% số tin, đúng {accuracy}
        </StatusChip>
      ) : (
        <StatusChip kind="warning">
          Đang tắt · độ chính xác hiện {accuracy} trên {status.samples ?? 0} tin mẫu (cần ≥ 95%)
        </StatusChip>
      )}
    </div>
  );
}
