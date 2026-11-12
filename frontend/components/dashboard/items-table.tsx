"use client";

import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, ExternalLink, Loader2, Search, XCircle } from "lucide-react";

import { cn } from "@/lib/utils";

import { ago, fetchItems, fmt, GROUP_LABEL, STAGE_LABEL, type Group, type ItemPage, type SourceRow } from "./api";

const GROUPS: Group[] = ["all", "processing", "published", "duplicate", "filtered", "failed"];
const PAGE_SIZE = 25;

export function ItemsTable({ sources, refreshKey }: { sources: SourceRow[]; refreshKey: number }) {
  const [group, setGroup] = useState<Group>("all");
  const [source, setSource] = useState("");
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<ItemPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), 300);
    return () => clearTimeout(t);
  }, [query]);

  // Back to page 1 whenever the filters change.
  useEffect(() => setPage(1), [group, source, debounced]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    fetchItems(
      { group, source: source || undefined, q: debounced || undefined, page, pageSize: PAGE_SIZE },
      controller.signal
    )
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => e.name !== "AbortError" && setError(e.message))
      .finally(() => !controller.signal.aborted && setLoading(false));
    return () => controller.abort();
  }, [group, source, debounced, page, refreshKey]);

  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <div>
      {/* filters: one row above the table */}
      <div className="mb-3 flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
        <div role="tablist" aria-label="Nhóm tin" className="no-scrollbar -mx-1 flex gap-1 overflow-x-auto px-1">
          {GROUPS.map((g) => (
            <button
              key={g}
              role="tab"
              type="button"
              aria-selected={group === g}
              onClick={() => setGroup(g)}
              className={cn(
                "inline-flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors",
                group === g
                  ? "bg-foreground text-background"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              {GROUP_LABEL[g]}
              <span className={cn("tabular-nums", group === g ? "opacity-70" : "opacity-60")}>
                {data ? fmt(data.counts[g]) : "·"}
              </span>
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <select
            value={source}
            onChange={(e) => setSource(e.target.value)}
            aria-label="Lọc theo nguồn"
            className="h-8 rounded-lg bg-muted px-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
          >
            <option value="">Mọi nguồn</option>
            {sources.map((s) => (
              <option key={s.slug} value={s.slug}>
                {s.name}
              </option>
            ))}
          </select>
          <label className="flex h-8 flex-1 items-center gap-1.5 rounded-lg bg-muted px-2 lg:w-56 lg:flex-none">
            <Search className="h-3.5 w-3.5 text-muted-foreground" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Tìm theo tiêu đề"
              aria-label="Tìm theo tiêu đề"
              className="min-w-0 flex-1 bg-transparent text-xs outline-none placeholder:text-muted-foreground"
            />
          </label>
        </div>
      </div>

      <div className="-mx-4 overflow-x-auto sm:-mx-5">
        <table className="w-full min-w-[52rem] text-sm">
          <thead className="border-b border-border">
            <tr className="text-left text-[0.6875rem] uppercase tracking-wide text-muted-foreground">
              <th className="px-3 py-2 pl-4 font-medium sm:pl-5">Tin</th>
              <th className="px-3 py-2 font-medium">Nguồn</th>
              <th className="px-3 py-2 font-medium">Trạng thái</th>
              <th className="px-3 py-2 font-medium">Chuyên mục</th>
              <th className="px-3 py-2 text-right font-medium">Liên quan</th>
              <th className="px-3 py-2 font-medium">Gom lúc</th>
              <th className="px-3 py-2 pr-4 font-medium sm:pr-5">Public lúc</th>
            </tr>
          </thead>
          <tbody className={cn(loading && "opacity-60 transition-opacity")}>
            {data?.items.map((item) => (
              <tr key={item.id} className="border-b border-border/60 last:border-0 hover:bg-muted/40">
                <td className="max-w-[26rem] px-3 py-2 pl-4 sm:pl-5">
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group inline-flex items-start gap-1 font-medium hover:text-primary"
                  >
                    <span className="line-clamp-2">{item.title}</span>
                    <ExternalLink className="mt-1 h-3 w-3 shrink-0 opacity-0 transition-opacity group-hover:opacity-60" />
                  </a>
                  {item.status_reason && (
                    <div className="mt-0.5 truncate text-[0.6875rem] text-muted-foreground" title={item.status_reason}>
                      {item.status_reason}
                    </div>
                  )}
                </td>
                <td className="whitespace-nowrap px-3 py-2 text-xs">{item.source_name}</td>
                <td className="whitespace-nowrap px-3 py-2 text-xs">
                  <span className="inline-flex items-center gap-1">
                    {item.group === "failed" && (
                      <XCircle className="h-3.5 w-3.5" style={{ color: "var(--status-critical)" }} />
                    )}
                    <span className={cn(item.group === "published" ? "font-semibold" : "text-muted-foreground")}>
                      {item.group === "processing"
                        ? (STAGE_LABEL[item.status] ?? item.status)
                        : GROUP_LABEL[item.group]}
                    </span>
                  </span>
                </td>
                <td className="whitespace-nowrap px-3 py-2 text-xs text-muted-foreground">{item.topic ?? "—"}</td>
                <td className="px-3 py-2 text-right text-xs tabular-nums">{item.relevance ?? "—"}</td>
                <td className="whitespace-nowrap px-3 py-2 text-xs text-muted-foreground">{ago(item.discovered_at)}</td>
                <td className="whitespace-nowrap px-3 py-2 pr-4 text-xs text-muted-foreground sm:pr-5">
                  {item.group === "published" ? ago(item.enriched_at) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && data.items.length === 0 && (
          <p className="py-10 text-center text-sm text-muted-foreground">Không có tin nào khớp bộ lọc.</p>
        )}
        {error && <p className="py-6 text-center text-sm text-muted-foreground">Không tải được danh sách: {error}</p>}
        {!data && !error && (
          <div className="flex justify-center py-10">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        )}
      </div>

      {data && data.total > PAGE_SIZE && (
        <div className="mt-3 flex items-center justify-end gap-2 text-xs text-muted-foreground">
          <span className="tabular-nums">
            Trang {page} / {pages} · {fmt(data.total)} tin
          </span>
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            aria-label="Trang trước"
            className="flex h-7 w-7 items-center justify-center rounded-lg hover:bg-muted disabled:opacity-40"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => setPage((p) => Math.min(pages, p + 1))}
            disabled={page >= pages}
            aria-label="Trang sau"
            className="flex h-7 w-7 items-center justify-center rounded-lg hover:bg-muted disabled:opacity-40"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
}
