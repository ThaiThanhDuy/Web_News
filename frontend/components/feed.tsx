"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowUp, Loader2 } from "lucide-react";

import { FeedPost } from "@/components/feed-post";
import { Reveal } from "@/components/reveal";
import { Skeleton } from "@/components/ui/skeleton";
import type { Article } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const NEW_POSTS_POLL_MS = 45_000;

export function Feed({
  initialItems,
  initialPage,
  pageSize,
  initialHasMore,
  category,
  source,
}: {
  initialItems: Article[];
  initialPage: number;
  pageSize: number;
  initialHasMore: boolean;
  category?: string;
  source?: string;
}) {
  const [items, setItems] = useState<Article[]>(initialItems);
  const [page, setPage] = useState(initialPage);
  const [hasMore, setHasMore] = useState(initialHasMore);
  const [loadingMore, setLoadingMore] = useState(false);
  const [newCount, setNewCount] = useState(0);
  const [loadingNew, setLoadingNew] = useState(false);

  const sentinelRef = useRef<HTMLDivElement>(null);
  const loadingMoreRef = useRef(false);
  const itemsRef = useRef(items);
  itemsRef.current = items;

  const buildQuery = useCallback(
    (extra: Record<string, string>) => {
      const query = new URLSearchParams(extra);
      if (category) query.set("category", category);
      if (source) query.set("source", source);
      return query;
    },
    [category, source]
  );

  const loadMore = useCallback(async () => {
    if (loadingMoreRef.current || !hasMore) return;
    loadingMoreRef.current = true;
    setLoadingMore(true);
    try {
      const nextPage = page + 1;
      const query = buildQuery({ sort: "feed", page: String(nextPage), page_size: String(pageSize) });
      const res = await fetch(`${API_BASE}/api/articles?${query.toString()}`);
      const data = await res.json();
      setItems((prev) => [...prev, ...data.items]);
      setPage(nextPage);
      setHasMore(Boolean(data.has_more));
    } catch {
      setHasMore(false);
    } finally {
      loadingMoreRef.current = false;
      setLoadingMore(false);
    }
  }, [hasMore, page, pageSize, buildQuery]);

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el || !hasMore) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) loadMore();
      },
      { rootMargin: "600px" }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [loadMore, hasMore]);

  // Poll for newly-published articles so we can show a Facebook-style
  // "N bài viết mới" pill instead of making people refresh the page.
  useEffect(() => {
    const checkNew = async () => {
      const latestSeenAt = itemsRef.current.reduce(
        (max, a) => (a.published_at > max ? a.published_at : max),
        itemsRef.current[0]?.published_at ?? new Date(0).toISOString()
      );
      try {
        const query = buildQuery({ since: latestSeenAt });
        const res = await fetch(`${API_BASE}/api/articles/new-count?${query.toString()}`);
        const data = await res.json();
        setNewCount(data.count ?? 0);
      } catch {
        // best-effort polling — ignore failures
      }
    };

    const interval = setInterval(checkNew, NEW_POSTS_POLL_MS);
    return () => clearInterval(interval);
  }, [buildQuery]);

  const loadNew = useCallback(async () => {
    setLoadingNew(true);
    try {
      const query = buildQuery({ sort: "feed", page: "1", page_size: String(pageSize) });
      const res = await fetch(`${API_BASE}/api/articles?${query.toString()}`);
      const data = await res.json();
      const existingIds = new Set(itemsRef.current.map((a) => a.id));
      const fresh = ((data.items ?? []) as Article[]).filter((a) => !existingIds.has(a.id));
      if (fresh.length > 0) {
        setItems((prev) => [...fresh, ...prev]);
      }
      window.scrollTo({ top: 0, behavior: "smooth" });
    } finally {
      setNewCount(0);
      setLoadingNew(false);
    }
  }, [buildQuery, pageSize]);

  return (
    <div className="relative">
      {newCount > 0 && (
        <div className="fixed left-1/2 top-28 z-30 -translate-x-1/2 animate-fade-in">
          <button
            onClick={loadNew}
            disabled={loadingNew}
            className="glass-sheen inline-flex items-center gap-1.5 rounded-full bg-gradient-to-r from-primary to-secondary px-4 py-2 text-sm font-semibold text-primary-foreground shadow-lg shadow-primary/30 transition-transform hover:scale-105 disabled:opacity-70"
          >
            {loadingNew ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-4 w-4" />}
            {newCount} bài viết mới
          </button>
        </div>
      )}

      <div className="space-y-4">
        {items.map((article, i) => (
          <Reveal key={article.id} delay={i < pageSize ? Math.min(i * 60, 300) : 0}>
            <FeedPost article={article} priority={i === 0} />
          </Reveal>
        ))}

        {loadingMore && (
          <>
            <PostSkeleton />
            <PostSkeleton />
          </>
        )}

        {hasMore ? (
          <div ref={sentinelRef} className="h-1" />
        ) : (
          <p className="py-10 text-center text-sm text-muted-foreground">Bạn đã xem hết tin mới.</p>
        )}
      </div>
    </div>
  );
}

function PostSkeleton() {
  return (
    <div className="glass-card space-y-3 rounded-2xl p-5">
      <div className="flex items-center gap-2">
        <Skeleton className="h-7 w-7 rounded-full" />
        <div className="space-y-1.5">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="h-2.5 w-14" />
        </div>
      </div>
      <Skeleton className="h-5 w-4/5" />
      <Skeleton className="h-4 w-2/3" />
      <Skeleton className="aspect-[16/9] w-full" />
    </div>
  );
}
