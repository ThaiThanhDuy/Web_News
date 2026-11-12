// Reader interest profile (part C), kept ONLY in this browser. Built from
// what the reader opens / which hashtags they click; scores decay with a
// 14-day half-life. Sent with feed requests to personalize the featured
// stories — the server uses it for that response and never stores it.

import { useCallback, useEffect, useState } from "react";

const PROFILE_KEY = "techdigest:interests";
const ENABLED_KEY = "techdigest:personalize";
const CHANGE_EVENT = "techdigest:interests";
const HALF_LIFE_DAYS = 14;
const MAX_ENTRIES = 60;

interface Entry {
  w: number; // score at time t
  t: number; // ms timestamp
}

interface Profile {
  topics: Record<string, Entry>;
  tags: Record<string, Entry>;
  labels: Record<string, string>; // folded tag -> display spelling
}

const empty = (): Profile => ({ topics: {}, tags: {}, labels: {} });

/** Same folding as the backend's fold_tag(): "iPhone 18" -> "iphone18". */
export function foldTag(value: string): string {
  return value.toLowerCase().replace(/đ/g, "d").normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/\s+/g, "");
}

function decayed(entry: Entry, now: number): number {
  return entry.w * Math.pow(0.5, (now - entry.t) / (HALF_LIFE_DAYS * 86_400_000));
}

function load(): Profile {
  try {
    const raw = localStorage.getItem(PROFILE_KEY);
    return raw ? { ...empty(), ...(JSON.parse(raw) as Profile) } : empty();
  } catch {
    return empty();
  }
}

function prune(map: Record<string, Entry>, now: number): Record<string, Entry> {
  return Object.fromEntries(
    Object.entries(map)
      .map(([k, e]) => [k, { w: decayed(e, now), t: now }] as const)
      .filter(([, e]) => e.w >= 0.05)
      .sort((a, b) => b[1].w - a[1].w)
      .slice(0, MAX_ENTRIES)
  );
}

function save(profile: Profile): void {
  const now = Date.now();
  const tags = prune(profile.tags, now);
  const next: Profile = {
    topics: prune(profile.topics, now),
    tags,
    labels: Object.fromEntries(Object.entries(profile.labels).filter(([k]) => k in tags)),
  };
  try {
    localStorage.setItem(PROFILE_KEY, JSON.stringify(next));
  } catch {
    // storage unavailable: personalization just stays off
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

function bump(map: Record<string, Entry>, key: string, amount: number, now: number) {
  const current = map[key] ? decayed(map[key], now) : 0;
  map[key] = { w: current + amount, t: now };
}

export function recordInterest(params: {
  topic?: string | null;
  tags?: string[];
  topicWeight?: number;
  tagWeight?: number;
}) {
  if (!personalizationEnabled()) return;
  const now = Date.now();
  const profile = load();
  if (params.topic) bump(profile.topics, params.topic, params.topicWeight ?? 1, now);
  for (const tag of params.tags ?? []) {
    const key = foldTag(tag);
    if (!key) continue;
    bump(profile.tags, key, params.tagWeight ?? 0.5, now);
    profile.labels[key] = tag;
  }
  save(profile);
}

export function clearInterests(): void {
  try {
    localStorage.removeItem(PROFILE_KEY);
  } catch {
    // ignore
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

export function personalizationEnabled(): boolean {
  try {
    return localStorage.getItem(ENABLED_KEY) !== "off";
  } catch {
    return false;
  }
}

export function setPersonalizationEnabled(on: boolean): void {
  try {
    localStorage.setItem(ENABLED_KEY, on ? "on" : "off");
  } catch {
    // ignore
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

/** Top interests as normalized 0..1 weights, ready for the feed API. */
export function interestParams(): { for_topics?: string; for_tags?: string } {
  if (!personalizationEnabled()) return {};
  const now = Date.now();
  const profile = load();
  const encode = (map: Record<string, Entry>, limit: number) => {
    const entries = Object.entries(map)
      .map(([k, e]) => [k, decayed(e, now)] as const)
      .filter(([, w]) => w >= 0.5)
      .sort((a, b) => b[1] - a[1])
      .slice(0, limit);
    const max = entries[0]?.[1] ?? 0;
    return entries.map(([k, w]) => `${k}:${(w / max).toFixed(2)}`).join(",");
  };
  const topics = encode(profile.topics, 8);
  const tags = encode(profile.tags, 20);
  return { ...(topics ? { for_topics: topics } : {}), ...(tags ? { for_tags: tags } : {}) };
}

export interface InterestSummary {
  enabled: boolean;
  topics: { slug: string; weight: number }[];
  tags: { key: string; label: string; weight: number }[];
}

function summarize(): InterestSummary {
  const now = Date.now();
  const profile = load();
  const top = (map: Record<string, Entry>, limit: number) =>
    Object.entries(map)
      .map(([k, e]) => [k, decayed(e, now)] as const)
      .filter(([, w]) => w >= 0.5)
      .sort((a, b) => b[1] - a[1])
      .slice(0, limit);
  return {
    enabled: personalizationEnabled(),
    topics: top(profile.topics, 5).map(([slug, weight]) => ({ slug, weight })),
    tags: top(profile.tags, 8).map(([key, weight]) => ({ key, label: profile.labels[key] ?? key, weight })),
  };
}

/** Live view of the profile for the settings popup. */
export function useInterests(): [InterestSummary, (on: boolean) => void, () => void] {
  const [summary, setSummary] = useState<InterestSummary>({ enabled: true, topics: [], tags: [] });
  useEffect(() => {
    const update = () => setSummary(summarize());
    update();
    window.addEventListener(CHANGE_EVENT, update);
    return () => window.removeEventListener(CHANGE_EVENT, update);
  }, []);
  return [summary, useCallback((on: boolean) => setPersonalizationEnabled(on), []), clearInterests];
}

/** Changes when personalization is toggled or cleared (not on every click,
 *  so feeds don't reshuffle while being read). */
export function usePersonalizationKey(): string {
  const [key, setKey] = useState("");
  useEffect(() => {
    const snapshot = () => JSON.stringify(interestParams());
    setKey(snapshot());
    const onChange = () => {
      const next = snapshot();
      // Only toggles/clears (profile emptied or personalization switched)
      // should reload the feed; ordinary clicks just enrich the profile.
      setKey((prev) => (next === "{}" || prev === "{}" ? next : prev));
    };
    window.addEventListener(CHANGE_EVENT, onChange);
    return () => window.removeEventListener(CHANGE_EVENT, onChange);
  }, []);
  return key;
}
