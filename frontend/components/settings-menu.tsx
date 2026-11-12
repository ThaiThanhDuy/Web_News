"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Flame, Languages, Settings, Sparkles } from "lucide-react";

import { getCategoryMeta } from "@/lib/category-meta";
import { useInterests } from "@/lib/interests";
import { MAX_HOT_COUNT, useHotCount, useLangs, type Lang } from "@/lib/settings";
import type { Category } from "@/lib/types";
import { headerIconButton } from "@/lib/ui";
import { cn } from "@/lib/utils";

/** Gear button + settings popup (same placement/behavior as the
 *  notifications popup). Add further sections below the existing ones. */
export function SettingsMenu({ categories }: { categories: Category[] }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  // Close on outside click / Escape.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(headerIconButton, open && "bg-muted text-foreground")}
        aria-label="Cài đặt"
        title="Cài đặt"
        aria-haspopup="dialog"
        aria-expanded={open}
      >
        <Settings
          className={cn(
            "h-4 w-4 transition-transform duration-300 ease-out motion-reduce:transition-none",
            open && "rotate-90"
          )}
        />
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Cài đặt"
          className="absolute right-0 top-10 z-40 w-[min(20rem,calc(100vw-2rem))] animate-palette-in rounded-2xl border border-border bg-background p-4 shadow-xl motion-reduce:animate-none"
        >
          <div className="text-sm font-bold">Cài đặt</div>
          <div className="mt-3 space-y-4">
            <LanguageSetting />
            <HotCountSetting />
            <PersonalizationSetting categories={categories} />
            {/* More settings sections go here. */}
          </div>
        </div>
      )}
    </div>
  );
}

/** Range 0-10: how many hottest stories lead each category's feed. */
function HotCountSetting() {
  const [hotCount, setHotCount] = useHotCount();
  const percent = (hotCount / MAX_HOT_COUNT) * 100;

  return (
    <section className="border-t border-border pt-4">
      <div className="flex items-center justify-between gap-3">
        <label htmlFor="hot-count" className="inline-flex items-center gap-1.5 text-sm font-medium">
          <Flame className="h-4 w-4 text-flame" />
          Tin nổi bật mỗi lĩnh vực
        </label>
        <span className="min-w-[2.5rem] rounded-md bg-muted px-2 py-0.5 text-center text-sm font-semibold tabular-nums">
          {hotCount}
        </span>
      </div>
      <input
        id="hot-count"
        type="range"
        min={0}
        max={MAX_HOT_COUNT}
        step={1}
        value={hotCount}
        onChange={(e) => setHotCount(Number(e.target.value))}
        aria-valuetext={`${hotCount} tin`}
        // The filled part of the track follows the value.
        style={{
          background: `linear-gradient(to right, hsl(var(--primary)) ${percent}%, hsl(var(--muted)) ${percent}%)`,
        }}
        className={cn(
          "mt-3 h-1.5 w-full cursor-pointer appearance-none rounded-full outline-none",
          "focus-visible:ring-2 focus-visible:ring-primary/50 focus-visible:ring-offset-2 focus-visible:ring-offset-background",
          // Thumb: solid primary dot with a background-colored ring (separates
          // it from the filled track) and a soft shadow — visible in both
          // themes. border-solid is required: Tailwind's preflight doesn't
          // reach slider-thumb pseudo-elements.
          "[&::-webkit-slider-thumb]:h-[1.125rem] [&::-webkit-slider-thumb]:w-[1.125rem] [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border-[3px] [&::-webkit-slider-thumb]:border-solid [&::-webkit-slider-thumb]:border-background [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:shadow-[0_1px_4px_rgba(0,0,0,0.35)] [&::-webkit-slider-thumb]:transition-transform [&::-webkit-slider-thumb]:hover:scale-110 [&::-webkit-slider-thumb]:active:scale-110",
          "[&::-moz-range-thumb]:h-[1.125rem] [&::-moz-range-thumb]:w-[1.125rem] [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-[3px] [&::-moz-range-thumb]:border-solid [&::-moz-range-thumb]:border-background [&::-moz-range-thumb]:bg-primary [&::-moz-range-thumb]:shadow-[0_1px_4px_rgba(0,0,0,0.35)]"
        )}
      />
      <div className="mt-1 flex justify-between text-[0.625rem] text-muted-foreground">
        <span>0</span>
        <span>{Math.round(MAX_HOT_COUNT / 2)}</span>
        <span>{MAX_HOT_COUNT}</span>
      </div>
    </section>
  );
}

/** Part C: interest-based ordering of featured stories, with the profile
 *  shown so readers see what it's based on and can wipe it. */
function PersonalizationSetting({ categories }: { categories: Category[] }) {
  const [interests, setEnabled, clear] = useInterests();
  const names = Object.fromEntries(categories.map((c) => [c.slug, c.name]));
  const empty = interests.topics.length === 0 && interests.tags.length === 0;

  return (
    <section className="border-t border-border pt-4">
      <div className="flex items-center justify-between gap-3">
        <span id="personalize-label" className="inline-flex items-center gap-1.5 text-sm font-medium">
          <Sparkles className="h-4 w-4 text-primary" />
          Ưu tiên tin hợp gu bạn
        </span>
        <button
          type="button"
          role="switch"
          aria-checked={interests.enabled}
          aria-labelledby="personalize-label"
          onClick={() => setEnabled(!interests.enabled)}
          className={cn(
            "relative h-5 w-9 shrink-0 rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50",
            interests.enabled ? "bg-primary" : "bg-muted-foreground/30"
          )}
        >
          <span
            className={cn(
              // Anchored to the left edge; slides 1rem: 2.25rem track, 1rem knob, 0.125rem inset.
              "absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-transform motion-reduce:transition-none",
              interests.enabled ? "translate-x-4" : "translate-x-0"
            )}
          />
        </button>
      </div>

      {interests.enabled && !empty && (
        <div className="mt-2.5 space-y-2">
          <div className="flex flex-wrap gap-1.5">
            {interests.topics.map((t) => (
              <span
                key={t.slug}
                className={cn("rounded-full px-2 py-0.5 text-[0.6875rem] font-medium", getCategoryMeta(t.slug).chip)}
              >
                {names[t.slug] ?? t.slug}
              </span>
            ))}
            {interests.tags.map((t) => (
              <span key={t.key} className="rounded-full bg-muted px-2 py-0.5 text-[0.6875rem] text-muted-foreground">
                #{t.label}
              </span>
            ))}
          </div>
          <button
            type="button"
            onClick={clear}
            className="text-xs font-medium text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
          >
            Xóa dữ liệu sở thích
          </button>
        </div>
      )}
    </section>
  );
}

const LANG_OPTIONS: { value: Lang; label: string }[] = [
  { value: "vi", label: "Tiếng Việt" },
  { value: "en", label: "English" },
];

/** Which article languages the feeds show; both = everything. */
function LanguageSetting() {
  const [langs, toggle] = useLangs();
  return (
    <section>
      <div className="mb-2 inline-flex items-center gap-1.5 text-sm font-medium">
        <Languages className="h-4 w-4 text-primary" />
        Ngôn ngữ tin
      </div>
      <div className="grid grid-cols-2 gap-2" role="group" aria-label="Ngôn ngữ tin">
        {LANG_OPTIONS.map((option) => {
          const on = langs.includes(option.value);
          const last = on && langs.length === 1;
          return (
            <button
              key={option.value}
              type="button"
              aria-pressed={on}
              disabled={last}
              title={last ? "Cần chọn ít nhất một ngôn ngữ" : undefined}
              onClick={() => toggle(option.value)}
              className={cn(
                "flex h-9 items-center justify-center gap-1.5 rounded-lg text-sm font-medium transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 disabled:cursor-not-allowed",
                on ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:text-foreground"
              )}
            >
              {on && <Check className="h-3.5 w-3.5" />}
              {option.label}
            </button>
          );
        })}
      </div>
    </section>
  );
}
