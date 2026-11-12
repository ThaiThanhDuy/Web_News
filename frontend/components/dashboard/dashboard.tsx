"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";

import { fetchSummary, type Summary } from "./api";
import { ItemsTable } from "./items-table";
import {
  Card,
  EngagementPanel,
  LocalClassifierStatus,
  QueuesTable,
  SearchMeters,
  SourcesTable,
  StageMeters,
  StatTiles,
  TokenMeters,
  TrendMeters,
} from "./parts";
import { TimelineChart } from "./timeline-chart";

const REFRESH_MS = 15_000;

/** Ops dashboard: collected / processing / published items, sources, queues. */
export function Dashboard() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [auto, setAuto] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setSummary(await fetchSummary());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Không tải được dữ liệu");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Auto-refresh while the tab is visible.
  useEffect(() => {
    if (!auto) return;
    const tick = () => {
      if (document.visibilityState === "visible") {
        load();
        setRefreshKey((k) => k + 1);
      }
    };
    const id = setInterval(tick, REFRESH_MS);
    document.addEventListener("visibilitychange", tick);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [auto, load]);

  const refresh = () => {
    load();
    setRefreshKey((k) => k + 1);
  };

  return (
    <div className="viz-root space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-xs text-muted-foreground">
            Tin đã gom, đang xử lý và đã public
            {summary && ` · cập nhật ${new Date(summary.generated_at).toLocaleTimeString("vi-VN", { hour12: false })}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="inline-flex cursor-pointer items-center gap-1.5 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={auto}
              onChange={(e) => setAuto(e.target.checked)}
              className="accent-[hsl(var(--primary))]"
            />
            Tự làm mới 15 giây
          </label>
          <button
            type="button"
            onClick={refresh}
            disabled={loading}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-muted px-3 text-xs font-medium transition-colors hover:bg-muted/70 disabled:opacity-60"
          >
            {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            Làm mới
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-border bg-card px-4 py-3 text-sm text-muted-foreground">{error}</div>
      )}

      {!summary && !error && (
        <div className="flex justify-center py-24">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {summary && (
        <>
          <StatTiles totals={summary.totals} />

          <div className="grid gap-4 lg:grid-cols-3">
            <Card title="Gom vào & public theo giờ (24 giờ)" className="lg:col-span-2">
              <TimelineChart points={summary.timeline} />
            </Card>
            <Card title="Pipeline">
              <StageMeters stages={summary.stages} />
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card title="Keyword đang lên (24 giờ)">
              <TrendMeters trends={summary.trends} />
            </Card>
            <Card title="Tương tác người đọc (24 giờ)">
              <EngagementPanel engagement={summary.engagement} />
            </Card>
            <Card title="Tìm kiếm nhiều nhất (7 ngày)">
              <SearchMeters searches={summary.top_searches} />
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card title="Hàng đợi (job pool)" className="lg:col-span-2">
              <QueuesTable queues={summary.queues} />
            </Card>
            <Card title="Token AI hôm nay">
              <TokenMeters tokens={summary.tokens} provider={summary.provider} />
              <LocalClassifierStatus status={summary.local_classifier} />
            </Card>
          </div>

          <Card title="Nguồn tin">
            <SourcesTable sources={summary.sources} />
          </Card>

          <Card title="Danh sách tin">
            <ItemsTable sources={summary.sources} refreshKey={refreshKey} />
          </Card>
        </>
      )}
    </div>
  );
}
