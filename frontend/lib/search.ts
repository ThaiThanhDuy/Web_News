// Client-side search helpers: API calls, the "open search" event, recent
// searches, and accent-insensitive highlighting.

import type { Article, Category } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const OPEN_EVENT = "techdigest:open-search";
const RECENT_KEY = "techdigest:recent-searches";
const MAX_RECENT = 6;

export interface SearchResult {
  query: string;
  items: Article[];
  related: Article[];
  topics: Category[];
  tags: string[];
}

export async function searchApi(q: string, signal?: AbortSignal): Promise<SearchResult> {
  const res = await fetch(`${API_BASE}/api/search?${new URLSearchParams({ q })}`, { signal });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function trendingApi(): Promise<string[]> {
  const res = await fetch(`${API_BASE}/api/search/trending`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()).tags ?? [];
}

/** Opens the search palette from anywhere (e.g. clicking a #hashtag). */
export function openSearch(query = ""): void {
  window.dispatchEvent(new CustomEvent<string>(OPEN_EVENT, { detail: query }));
}

export function onOpenSearch(handler: (query: string) => void): () => void {
  const listener = (e: Event) => handler((e as CustomEvent<string>).detail ?? "");
  window.addEventListener(OPEN_EVENT, listener);
  return () => window.removeEventListener(OPEN_EVENT, listener);
}

// Recent searches are a per-browser convenience; storage may be unavailable.
export function loadRecent(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    return raw ? (JSON.parse(raw) as string[]).slice(0, MAX_RECENT) : [];
  } catch {
    return [];
  }
}

export function saveRecent(query: string): string[] {
  const q = query.trim();
  if (!q) return loadRecent();
  const next = [q, ...loadRecent().filter((r) => r.toLowerCase() !== q.toLowerCase())].slice(0, MAX_RECENT);
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    // ignore
  }
  return next;
}

export function clearRecent(): void {
  try {
    localStorage.removeItem(RECENT_KEY);
  } catch {
    // ignore
  }
}

/** Accent-free lowercase, one output char per input char (so indexes line
 *  up with the original string for highlighting). */
export function foldChars(value: string): string {
  let out = "";
  for (const ch of value.normalize("NFC")) {
    const base = ch.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
    out += ch === "đ" || ch === "Đ" ? "d" : base.length === 1 ? base : ch.toLowerCase();
  }
  return out;
}

export interface Segment {
  text: string;
  match: boolean;
}

/** Splits `text` into matched / unmatched parts for the query's words. */
export function highlight(text: string, query: string): Segment[] {
  const source = text.normalize("NFC");
  const folded = foldChars(source);
  const words = query
    .split(/\s+/)
    .map((w) => foldChars(w.replace(/^#/, "")))
    .filter((w) => w.length >= 2);
  if (!words.length || folded.length !== source.length) return [{ text: source, match: false }];

  const marks = new Array<boolean>(source.length).fill(false);
  for (const word of words) {
    let from = 0;
    for (let at = folded.indexOf(word, from); at !== -1; at = folded.indexOf(word, from)) {
      marks.fill(true, at, at + word.length);
      from = at + word.length;
    }
  }
  const segments: Segment[] = [];
  for (let i = 0; i < source.length; i++) {
    const last = segments[segments.length - 1];
    if (last && last.match === marks[i]) last.text += source[i];
    else segments.push({ text: source[i], match: marks[i] });
  }
  return segments;
}
