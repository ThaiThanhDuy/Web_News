// Types + fetchers for the read-only ops dashboard (/api/dashboard/*).

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Group = "all" | "processing" | "published" | "duplicate" | "filtered" | "failed";

export interface Totals {
  collected: number;
  processing: number;
  published: number;
  duplicate: number;
  filtered: number;
  failed: number;
  collected_24h: number;
  published_24h: number;
}

export interface TimelinePoint {
  hour: string;
  collected: number;
  published: number;
}

export interface SourceRow {
  slug: string;
  name: string;
  is_active: boolean;
  paused: boolean;
  collected: number;
  processing: number;
  published: number;
  duplicate: number;
  filtered: number;
  failed: number;
  last_fetch_at: string | null;
  last_success_at: string | null;
  next_run_at: string | null;
  consecutive_failures: number;
  last_error: string | null;
}

export interface QueueRow {
  queue: string;
  due: number;
  scheduled: number;
  running: number;
  done_1h: number;
  dead: number;
  oldest_due_seconds: number | null;
}

export interface TokenRow {
  model: string;
  stages: string[];
  used: number;
  cap: number;
}

export interface TrendRow {
  keyword: string;
  recent_24h: number;
  sources_24h: number;
  baseline_daily: number;
  lift: number;
  heat: number;
}

export interface EngagementSummary {
  impressions_24h: number;
  clicks_24h: number;
  tag_clicks_24h: number;
  push_opens_24h: number;
  searches_24h: number;
  in_ranking: boolean;
  min_daily_impressions: number;
  top_clicked: { id: number; title: string; url: string; impressions: number; clicks: number }[];
}

export interface Summary {
  generated_at: string;
  totals: Totals;
  stages: { status: string; count: number }[];
  timeline: TimelinePoint[];
  sources: SourceRow[];
  queues: QueueRow[];
  tokens: TokenRow[];
  provider: string;
  trends: TrendRow[];
  top_searches: { query: string; count: number }[];
  engagement: EngagementSummary;
  local_classifier: {
    active: boolean;
    samples?: number;
    decided_share?: number;
    keep_drop_accuracy?: number;
    reason?: string | null;
  };
}

export interface ItemRow {
  id: number;
  title: string;
  url: string;
  source_slug: string;
  source_name: string;
  status: string;
  group: Group;
  status_reason: string | null;
  topic: string | null;
  relevance: number | null;
  item_type: string;
  discovered_at: string;
  published_at: string;
  enriched_at: string | null;
}

export interface ItemPage {
  items: ItemRow[];
  total: number;
  page: number;
  page_size: number;
  counts: Record<Group, number>;
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { signal, cache: "no-store" });
  if (!res.ok)
    throw new Error(res.status === 404 ? "Dashboard đang tắt (DASHBOARD_ENABLED=false)" : `HTTP ${res.status}`);
  return res.json();
}

export function fetchSummary(signal?: AbortSignal): Promise<Summary> {
  return get("/api/dashboard/summary", signal);
}

export function fetchItems(
  params: { group: Group; source?: string; q?: string; page: number; pageSize: number },
  signal?: AbortSignal
): Promise<ItemPage> {
  const query = new URLSearchParams({
    group: params.group,
    page: String(params.page),
    page_size: String(params.pageSize),
  });
  if (params.source) query.set("source", params.source);
  if (params.q) query.set("q", params.q);
  return get(`/api/dashboard/items?${query}`, signal);
}

// ---------------------------------------------------------------- labels

export const GROUP_LABEL: Record<Group, string> = {
  all: "Tất cả",
  processing: "Đang xử lý",
  published: "Đã public",
  duplicate: "Trùng / ẩn",
  filtered: "Bị lọc",
  failed: "Lỗi",
};

export const STAGE_LABEL: Record<string, string> = {
  discovered: "Mới gom (chờ tải trang)",
  fetched: "Đã tải trang",
  parsed: "Đã chuẩn hoá",
  ready: "Chờ AI phân loại",
  classified: "Chờ AI tóm tắt",
  enriched: "Đã xử lý xong",
  duplicate: "Trùng",
  filtered: "Bị lọc",
  failed: "Lỗi",
};

export const QUEUE_LABEL: Record<string, string> = {
  fetch: "Cào nguồn & tải trang",
  parse: "Chuẩn hoá",
  filter: "Lọc & chống trùng",
  ai_fast: "AI phân loại",
  ai_deep: "AI tóm tắt",
  deliver: "Gửi thông báo",
  maintenance: "Bảo trì",
};

// ---------------------------------------------------------------- format

const numberFormat = new Intl.NumberFormat("vi-VN");

export function fmt(n: number): string {
  return numberFormat.format(n);
}

export function compact(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(n >= 10_000 ? 0 : 1)}K` : String(n);
}

export function ago(iso: string | null): string {
  if (!iso) return "—";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  const future = diff < 0;
  const s = Math.abs(diff);
  const text =
    s < 60
      ? `${Math.round(s)} giây`
      : s < 3600
        ? `${Math.round(s / 60)} phút`
        : s < 86400
          ? `${Math.round(s / 3600)} giờ`
          : `${Math.round(s / 86400)} ngày`;
  return future ? `sau ${text}` : `${text} trước`;
}

export function duration(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${Math.round(seconds)} giây`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} phút`;
  return `${(seconds / 3600).toFixed(1)} giờ`;
}

export function hourLabel(iso: string): string {
  return new Date(iso).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", hour12: false });
}
