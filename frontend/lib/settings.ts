// Reader settings, stored per browser (no accounts yet). Every component
// using a setting re-renders when it changes, in this tab or another one.

import { useCallback, useEffect, useState } from "react";

const CHANGE_EVENT = "techdigest:settings";

/** How many hottest stories lead a category feed. Must match the backend's
 *  FEED_HOT_COUNT default (what server-rendered pages already contain). */
export const DEFAULT_HOT_COUNT = 5;
export const MAX_HOT_COUNT = 25;
const HOT_COUNT_KEY = "techdigest:hot-count";

export function readHotCount(): number {
  try {
    const raw = localStorage.getItem(HOT_COUNT_KEY);
    if (raw === null) return DEFAULT_HOT_COUNT;
    const value = Number.parseInt(raw, 10);
    return Number.isNaN(value) ? DEFAULT_HOT_COUNT : Math.min(MAX_HOT_COUNT, Math.max(0, value));
  } catch {
    return DEFAULT_HOT_COUNT;
  }
}

function writeHotCount(value: number): void {
  try {
    localStorage.setItem(HOT_COUNT_KEY, String(value));
  } catch {
    // storage unavailable (private mode...): the value still applies to this page
  }
  window.dispatchEvent(new CustomEvent<number>(CHANGE_EVENT, { detail: value }));
}

/** [value, setValue]; starts at the default until mounted (matches SSR). */
export function useHotCount(): [number, (value: number) => void] {
  const [value, setValue] = useState(DEFAULT_HOT_COUNT);

  useEffect(() => {
    setValue(readHotCount());
    // The same event also carries other settings (e.g. languages): only
    // react to numeric hot-count updates.
    const onLocal = (e: Event) => {
      const detail = (e as CustomEvent<unknown>).detail;
      if (typeof detail === "number") setValue(detail);
    };
    const onOtherTab = (e: StorageEvent) => e.key === HOT_COUNT_KEY && setValue(readHotCount());
    window.addEventListener(CHANGE_EVENT, onLocal);
    window.addEventListener("storage", onOtherTab);
    return () => {
      window.removeEventListener(CHANGE_EVENT, onLocal);
      window.removeEventListener("storage", onOtherTab);
    };
  }, []);

  const update = useCallback((next: number) => {
    const clamped = Math.min(MAX_HOT_COUNT, Math.max(0, Math.round(next)));
    setValue(clamped);
    writeHotCount(clamped);
  }, []);

  return [value, update];
}

// ------------------------------------------------------------- languages

export type Lang = "vi" | "en";
export const ALL_LANGS: Lang[] = ["vi", "en"];
const LANGS_KEY = "techdigest:langs";

export function readLangs(): Lang[] {
  try {
    const raw = JSON.parse(localStorage.getItem(LANGS_KEY) ?? "null") as unknown;
    const langs = Array.isArray(raw) ? ALL_LANGS.filter((l) => raw.includes(l)) : [];
    return langs.length ? langs : ALL_LANGS;
  } catch {
    return ALL_LANGS;
  }
}

/** API `lang` value: one language selected → it; both → undefined (all). */
export function langParam(langs: Lang[]): Lang | undefined {
  return langs.length === 1 ? langs[0] : undefined;
}

/** [selected languages, toggle]. At least one always stays selected. */
export function useLangs(): [Lang[], (lang: Lang) => void] {
  const [langs, setLangs] = useState<Lang[]>(ALL_LANGS);

  useEffect(() => {
    setLangs(readLangs());
    const onLocal = (e: Event) => {
      const detail = (e as CustomEvent<{ langs?: Lang[] }>).detail;
      if (detail?.langs) setLangs(detail.langs);
    };
    const onOtherTab = (e: StorageEvent) => e.key === LANGS_KEY && setLangs(readLangs());
    window.addEventListener(CHANGE_EVENT, onLocal);
    window.addEventListener("storage", onOtherTab);
    return () => {
      window.removeEventListener(CHANGE_EVENT, onLocal);
      window.removeEventListener("storage", onOtherTab);
    };
  }, []);

  const toggle = useCallback((lang: Lang) => {
    const current = readLangs();
    const next = current.includes(lang)
      ? current.filter((l) => l !== lang)
      : ALL_LANGS.filter((l) => l === lang || current.includes(l));
    if (!next.length) return; // keep at least one
    try {
      localStorage.setItem(LANGS_KEY, JSON.stringify(next));
    } catch {
      // storage unavailable: still applies to this page
    }
    setLangs(next);
    window.dispatchEvent(new CustomEvent(CHANGE_EVENT, { detail: { langs: next } }));
  }, []);

  return [langs, toggle];
}
