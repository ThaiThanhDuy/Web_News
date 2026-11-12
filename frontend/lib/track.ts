// Anonymous engagement events (part B). Batched and sent with
// navigator.sendBeacon (text/plain → no CORS preflight, survives page
// unload). No identifiers are sent; browsers with Do Not Track on send
// nothing. Opening an article / clicking a hashtag also feeds the local
// interest profile (lib/interests.ts).

import { foldTag, recordInterest } from "./interests";
import type { Article } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const ENDPOINT = `${API_BASE}/api/events`;
const FLUSH_MS = 5000;
const MAX_BATCH = 50;

type EventType = "impression" | "click" | "tag_click" | "search";

interface TrackEvent {
  type: EventType;
  item_id?: number;
  position?: number;
  query?: string;
}

let queue: TrackEvent[] = [];
let timer: ReturnType<typeof setTimeout> | null = null;
const seenImpressions = new Set<number>();
const seenSearches = new Set<string>();
let listenersReady = false;

function disabled(): boolean {
  if (typeof navigator === "undefined") return true;
  return navigator.doNotTrack === "1" || (window as Window & { doNotTrack?: string }).doNotTrack === "1";
}

function flush(): void {
  if (timer) {
    clearTimeout(timer);
    timer = null;
  }
  while (queue.length) {
    const body = JSON.stringify({ events: queue.splice(0, MAX_BATCH) });
    const sent = typeof navigator.sendBeacon === "function" && navigator.sendBeacon(ENDPOINT, body);
    if (!sent) {
      fetch(ENDPOINT, { method: "POST", body, keepalive: true, headers: { "Content-Type": "text/plain" } }).catch(
        () => {}
      );
    }
  }
}

function enqueue(event: TrackEvent): void {
  if (disabled()) return;
  if (!listenersReady) {
    listenersReady = true;
    document.addEventListener("visibilitychange", () => document.visibilityState === "hidden" && flush());
    window.addEventListener("pagehide", flush);
  }
  queue.push(event);
  if (queue.length >= MAX_BATCH) flush();
  else if (!timer) timer = setTimeout(flush, FLUSH_MS);
}

/** Item seen in a feed (once per item per page session). */
export function trackImpression(itemId: number, position: number): void {
  if (seenImpressions.has(itemId)) return;
  seenImpressions.add(itemId);
  enqueue({ type: "impression", item_id: itemId, position });
}

/** Reader opened the article (title, image, "Đọc bài gốc", search result). */
export function trackOpen(article: Article, position?: number): void {
  enqueue({ type: "click", item_id: article.id, ...(position ? { position } : {}) });
  recordInterest({ topic: article.category?.slug, tags: article.keywords ?? [], topicWeight: 1, tagWeight: 0.5 });
}

export function trackTagClick(article: Article, tag: string): void {
  enqueue({ type: "tag_click", item_id: article.id });
  recordInterest({ tags: [tag], tagWeight: 1 });
}

/** A search the reader actually ran (once per distinct query per session). */
export function trackSearch(query: string): void {
  const key = foldTag(query);
  if (key.length < 2 || seenSearches.has(key)) return;
  seenSearches.add(key);
  enqueue({ type: "search", query: query.slice(0, 200) });
}
