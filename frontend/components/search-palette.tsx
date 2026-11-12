"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowUpRight, Clock, CornerDownLeft, Hash, Loader2, Search, Sparkles, TrendingUp, X } from "lucide-react";

import { getCategoryMeta } from "@/lib/category-meta";
import {
  clearRecent,
  highlight,
  loadRecent,
  onOpenSearch,
  saveRecent,
  searchApi,
  trendingApi,
  type SearchResult,
} from "@/lib/search";
import { langParam, readLangs } from "@/lib/settings";
import { relativeTimeVi } from "@/lib/time";
import { trackOpen, trackSearch } from "@/lib/track";
import type { Article, Category } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Search box in the header + the Ctrl/⌘+K command palette it opens. */
export function SearchLauncher() {
  const [open, setOpen] = useState(false);
  const [initialQuery, setInitialQuery] = useState("");
  const [shortcut, setShortcut] = useState("Ctrl K");
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (/Mac|iPhone|iPad/.test(navigator.platform)) setShortcut("⌘K");

    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const typing =
        target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setInitialQuery("");
        setOpen((v) => !v);
      } else if (e.key === "/" && !typing && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        setInitialQuery("");
        setOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    const off = onOpenSearch((query) => {
      setInitialQuery(query);
      setOpen(true);
    });
    return () => {
      window.removeEventListener("keydown", onKey);
      off();
    };
  }, []);

  const close = useCallback(() => {
    setOpen(false);
    triggerRef.current?.focus();
  }, []);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => {
          setInitialQuery("");
          setOpen(true);
        }}
        aria-label="Tìm kiếm"
        aria-keyshortcuts="Control+K Meta+K"
        className={cn(
          "flex h-8 items-center gap-2 rounded-lg bg-muted text-[0.8125rem] text-muted-foreground transition-colors",
          "w-8 justify-center hover:text-foreground",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50",
          "md:w-64 md:justify-start md:px-3 md:hover:bg-muted/70 lg:w-96"
        )}
      >
        <Search className="h-4 w-4 shrink-0" />
        <span className="hidden flex-1 truncate text-left md:inline">Tìm tin, #hashtag, chủ đề…</span>
        <kbd className="hidden rounded bg-background px-1.5 py-px font-sans text-[0.625rem] font-medium text-muted-foreground md:inline">
          {shortcut}
        </kbd>
      </button>

      {open && <SearchPalette key={initialQuery} initialQuery={initialQuery} onClose={close} />}
    </>
  );
}

// ---------------------------------------------------------------- palette

type Entry =
  | { kind: "query"; value: string; icon: "recent" | "trending" | "tag" }
  | { kind: "topic"; topic: Category }
  | { kind: "article"; article: Article; section: "items" | "related" };

let trendingCache: string[] | null = null;

function SearchPalette({ initialQuery, onClose }: { initialQuery: string; onClose: () => void }) {
  const router = useRouter();
  const [query, setQuery] = useState(initialQuery);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [trending, setTrending] = useState<string[]>(trendingCache ?? []);
  const [recent, setRecent] = useState<string[]>([]);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const trimmed = query.trim();

  // Mount: focus, lock page scroll, load recent + trending.
  useEffect(() => {
    inputRef.current?.focus();
    const length = inputRef.current?.value.length ?? 0;
    inputRef.current?.setSelectionRange(length, length);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    setRecent(loadRecent());
    if (!trendingCache) {
      trendingApi()
        .then((tags) => {
          trendingCache = tags;
          setTrending(tags);
        })
        .catch(() => {});
    }
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  // Debounced search; stale requests are aborted.
  useEffect(() => {
    if (!trimmed) {
      setResult(null);
      setLoading(false);
      setFailed(false);
      return;
    }
    setLoading(true);
    const controller = new AbortController();
    const timer = setTimeout(() => {
      searchApi(trimmed, controller.signal, langParam(readLangs()))
        .then((data) => {
          setResult(data);
          setFailed(false);
          setActive(0);
          trackSearch(trimmed);
        })
        .catch((err) => {
          if (err.name !== "AbortError") setFailed(true);
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 220);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [trimmed]);

  const entries = useMemo<Entry[]>(() => {
    if (!trimmed) {
      return [
        ...recent.map((value) => ({ kind: "query" as const, value, icon: "recent" as const })),
        ...trending.map((tag) => ({ kind: "query" as const, value: `#${tag}`, icon: "trending" as const })),
      ];
    }
    if (!result) return [];
    return [
      ...result.topics.map((topic) => ({ kind: "topic" as const, topic })),
      ...result.tags.map((tag) => ({ kind: "query" as const, value: `#${tag}`, icon: "tag" as const })),
      ...result.items.map((article) => ({ kind: "article" as const, article, section: "items" as const })),
      ...result.related.map((article) => ({ kind: "article" as const, article, section: "related" as const })),
    ];
  }, [trimmed, result, recent, trending]);

  useEffect(() => {
    listRef.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active]);

  const choose = (entry: Entry | undefined) => {
    if (!entry) return;
    if (entry.kind === "query") {
      setQuery(entry.value);
      setActive(0);
      inputRef.current?.focus();
      return;
    }
    if (trimmed) setRecent(saveRecent(trimmed));
    if (entry.kind === "topic") {
      router.push(`/category/${entry.topic.slug}`);
      onClose();
    } else {
      trackOpen(entry.article);
      window.open(entry.article.original_url, "_blank", "noopener,noreferrer");
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    } else if (e.key === "ArrowDown" && entries.length) {
      e.preventDefault();
      setActive((i) => (i + 1) % entries.length);
    } else if (e.key === "ArrowUp" && entries.length) {
      e.preventDefault();
      setActive((i) => (i - 1 + entries.length) % entries.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(entries[active]);
    }
  };

  // Index of each entry inside the flat keyboard-navigation list.
  let index = -1;
  const next = () => ++index;

  const queryChips = (items: Extract<Entry, { kind: "query" }>[]) =>
    items.map((entry) => {
      const i = next();
      const Icon = entry.icon === "recent" ? Clock : entry.icon === "trending" ? TrendingUp : Hash;
      return (
        <button
          key={`${entry.icon}-${entry.value}`}
          id={`search-opt-${i}`}
          data-index={i}
          role="option"
          aria-selected={active === i}
          type="button"
          onMouseEnter={() => setActive(i)}
          onClick={() => choose(entry)}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-all duration-200",
            active === i
              ? "border-primary/50 bg-primary/10 text-primary shadow-sm"
              : "border-border/70 bg-card/60 text-foreground/80 hover:border-primary/30"
          )}
        >
          <Icon className="h-3.5 w-3.5 opacity-70" />
          {entry.value}
        </button>
      );
    });

  const recentEntries = entries.filter(
    (e): e is Extract<Entry, { kind: "query" }> => e.kind === "query" && e.icon === "recent"
  );
  const trendingEntries = entries.filter(
    (e): e is Extract<Entry, { kind: "query" }> => e.kind === "query" && e.icon === "trending"
  );
  const tagEntries = entries.filter(
    (e): e is Extract<Entry, { kind: "query" }> => e.kind === "query" && e.icon === "tag"
  );
  const topicEntries = entries.filter((e): e is Extract<Entry, { kind: "topic" }> => e.kind === "topic");
  const itemEntries = entries.filter(
    (e): e is Extract<Entry, { kind: "article" }> => e.kind === "article" && e.section === "items"
  );
  const relatedEntries = entries.filter(
    (e): e is Extract<Entry, { kind: "article" }> => e.kind === "article" && e.section === "related"
  );
  const noResults = Boolean(trimmed && result && !loading && entries.length === 0);

  return (
    <div
      className="fixed inset-0 z-50 flex justify-center bg-black/40 px-3 pt-[8dvh] backdrop-blur-sm animate-fade-in motion-reduce:animate-none"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
      role="dialog"
      aria-modal="true"
      aria-label="Tìm kiếm"
    >
      <div className="flex h-fit max-h-[80dvh] w-full max-w-2xl animate-palette-in flex-col overflow-hidden rounded-2xl border border-border/70 bg-background/95 shadow-2xl shadow-primary/10 backdrop-blur-xl motion-reduce:animate-none">
        {/* input */}
        <div className="flex items-center gap-3 border-b border-border/60 px-4">
          {loading ? (
            <Loader2 className="h-5 w-5 shrink-0 animate-spin text-primary" />
          ) : (
            <Search className="h-5 w-5 shrink-0 text-muted-foreground" />
          )}
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Tìm theo từ khóa, #hashtag hoặc chủ đề…"
            role="combobox"
            aria-expanded={entries.length > 0}
            aria-controls="search-results"
            aria-activedescendant={entries.length ? `search-opt-${active}` : undefined}
            autoComplete="off"
            spellCheck={false}
            className="h-14 min-w-0 flex-1 bg-transparent text-base outline-none placeholder:text-muted-foreground/70"
          />
          {query && (
            <button
              type="button"
              onClick={() => {
                setQuery("");
                inputRef.current?.focus();
              }}
              className="rounded-lg p-1 text-muted-foreground transition hover:bg-muted hover:text-foreground"
              aria-label="Xóa"
            >
              <X className="h-4 w-4" />
            </button>
          )}
          <kbd className="hidden rounded-md border border-border/70 bg-muted/60 px-1.5 py-0.5 font-sans text-[0.625rem] font-semibold text-muted-foreground sm:inline">
            Esc
          </kbd>
        </div>

        {/* results */}
        <div ref={listRef} id="search-results" role="listbox" className="flex-1 space-y-4 overflow-y-auto p-3">
          {!trimmed && (
            <>
              {recentEntries.length > 0 && (
                <Section
                  title="Tìm gần đây"
                  action={
                    <button
                      type="button"
                      onClick={() => {
                        clearRecent();
                        setRecent([]);
                      }}
                      className="text-[0.6875rem] font-medium text-muted-foreground hover:text-foreground"
                    >
                      Xóa
                    </button>
                  }
                >
                  <div className="flex flex-wrap gap-1.5">{queryChips(recentEntries)}</div>
                </Section>
              )}
              {trendingEntries.length > 0 && (
                <Section title="Hashtag nổi bật 48 giờ qua">
                  <div className="flex flex-wrap gap-1.5">{queryChips(trendingEntries)}</div>
                </Section>
              )}
            </>
          )}

          {topicEntries.length > 0 && (
            <Section title="Chủ đề">
              <div className="flex flex-wrap gap-1.5">
                {topicEntries.map((entry) => {
                  const i = next();
                  const meta = getCategoryMeta(entry.topic.slug);
                  const Icon = meta.icon;
                  return (
                    <button
                      key={entry.topic.slug}
                      id={`search-opt-${i}`}
                      data-index={i}
                      role="option"
                      aria-selected={active === i}
                      type="button"
                      onMouseEnter={() => setActive(i)}
                      onClick={() => choose(entry)}
                      className={cn(
                        "inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold transition-all duration-200",
                        active === i ? cn("bg-gradient-to-r text-white shadow-md", meta.gradient, meta.glow) : meta.chip
                      )}
                    >
                      <Icon className="h-3.5 w-3.5" />
                      {entry.topic.name}
                      <ArrowUpRight className="h-3 w-3 opacity-70" />
                    </button>
                  );
                })}
              </div>
            </Section>
          )}

          {tagEntries.length > 0 && (
            <Section title="Hashtag">
              <div className="flex flex-wrap gap-1.5">{queryChips(tagEntries)}</div>
            </Section>
          )}

          {itemEntries.length > 0 && (
            <Section title={`Kết quả (${itemEntries.length})`}>
              <div className="space-y-1">
                {itemEntries.map((entry) => {
                  const i = next();
                  return (
                    <ArticleRow
                      key={entry.article.id}
                      index={i}
                      article={entry.article}
                      query={trimmed}
                      active={active === i}
                      onHover={() => setActive(i)}
                      onChoose={() => choose(entry)}
                    />
                  );
                })}
              </div>
            </Section>
          )}

          {relatedEntries.length > 0 && (
            <Section title="Có thể liên quan" icon={<Sparkles className="h-3 w-3 text-primary" />}>
              <div className="space-y-1">
                {relatedEntries.map((entry) => {
                  const i = next();
                  return (
                    <ArticleRow
                      key={entry.article.id}
                      index={i}
                      article={entry.article}
                      query=""
                      active={active === i}
                      onHover={() => setActive(i)}
                      onChoose={() => choose(entry)}
                    />
                  );
                })}
              </div>
            </Section>
          )}

          {noResults && (
            <div className="flex flex-col items-center gap-2 py-10 text-center">
              <Search className="h-8 w-8 text-muted-foreground/40" />
              <p className="text-sm font-semibold">Không tìm thấy tin nào cho “{trimmed}”</p>
              <p className="text-xs text-muted-foreground">
                Thử từ khóa khác, bỏ bớt từ, hoặc chọn một hashtag nổi bật.
              </p>
            </div>
          )}
          {failed && (
            <p className="py-6 text-center text-sm text-muted-foreground">Không kết nối được máy chủ. Thử lại sau.</p>
          )}
        </div>

        {/* footer */}
        <div className="hidden items-center gap-4 border-t border-border/60 px-4 py-2 text-[0.6875rem] text-muted-foreground sm:flex">
          <span className="inline-flex items-center gap-1">
            <Kbd>↑</Kbd>
            <Kbd>↓</Kbd> chọn
          </span>
          <span className="inline-flex items-center gap-1">
            <Kbd>
              <CornerDownLeft className="h-3 w-3" />
            </Kbd>
            mở
          </span>
          <span className="inline-flex items-center gap-1">
            <Kbd>Esc</Kbd> đóng
          </span>
        </div>
      </div>
    </div>
  );
}

function Section({
  title,
  icon,
  action,
  children,
}: {
  title: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="animate-fade-in motion-reduce:animate-none">
      <div className="mb-1.5 flex items-center justify-between px-1">
        <h3 className="inline-flex items-center gap-1.5 text-[0.6875rem] font-semibold uppercase tracking-wide text-muted-foreground">
          {icon}
          {title}
        </h3>
        {action}
      </div>
      {children}
    </section>
  );
}

function ArticleRow({
  article,
  query,
  index,
  active,
  onHover,
  onChoose,
}: {
  article: Article;
  query: string;
  index: number;
  active: boolean;
  onHover: () => void;
  onChoose: () => void;
}) {
  const meta = getCategoryMeta(article.category?.slug);
  return (
    <button
      id={`search-opt-${index}`}
      data-index={index}
      role="option"
      aria-selected={active}
      type="button"
      onMouseEnter={onHover}
      onClick={onChoose}
      className={cn(
        "group flex w-full items-start gap-3 rounded-xl p-2 text-left transition-all duration-200",
        active ? "bg-primary/10 ring-1 ring-primary/30" : "hover:bg-muted/60"
      )}
    >
      <span className="relative h-12 w-16 shrink-0 overflow-hidden rounded-lg bg-muted ring-1 ring-border/60">
        {article.thumbnail_url && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={article.thumbnail_url}
            alt=""
            loading="lazy"
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
          />
        )}
      </span>
      <span className="min-w-0 flex-1">
        <span className="line-clamp-2 text-sm font-semibold leading-snug">
          <Highlighted text={article.title} query={query} />
        </span>
        {article.one_line_takeaway && (
          <span className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">
            <Highlighted text={article.one_line_takeaway} query={query} />
          </span>
        )}
        <span className="mt-1 flex items-center gap-1.5 text-[0.6875rem] text-muted-foreground">
          <span className="font-medium text-foreground/70">{article.source.name}</span>
          <span>·</span>
          <span>{relativeTimeVi(article.published_at)}</span>
          {article.category && (
            <span className={cn("ml-1 rounded-full px-1.5 py-px font-medium", meta.chip)}>{article.category.name}</span>
          )}
        </span>
      </span>
      <ArrowUpRight
        className={cn(
          "mt-1 h-4 w-4 shrink-0 text-muted-foreground transition-all duration-200",
          active ? "translate-x-0.5 -translate-y-0.5 text-primary opacity-100" : "opacity-0 group-hover:opacity-100"
        )}
      />
    </button>
  );
}

function Highlighted({ text, query }: { text: string; query: string }) {
  if (!query) return <>{text}</>;
  return (
    <>
      {highlight(text, query).map((segment, i) =>
        segment.match ? (
          <mark key={i} className="rounded bg-primary/15 px-0.5 text-primary">
            {segment.text}
          </mark>
        ) : (
          <span key={i}>{segment.text}</span>
        )
      )}
    </>
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex min-w-[1.25rem] items-center justify-center rounded border border-border/70 bg-muted/60 px-1 py-px font-sans text-[0.625rem] font-semibold">
      {children}
    </kbd>
  );
}
