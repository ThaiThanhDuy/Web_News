import type { ArticlePage, Category, Source } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function safeFetch<T>(path: string, revalidate: number, fallback: T): Promise<T> {
  try {
    const res = await fetch(`${API_BASE}${path}`, { next: { revalidate } });
    if (!res.ok) return fallback;
    return (await res.json()) as T;
  } catch {
    // Backend not reachable (e.g. during a build without the API running) —
    // degrade gracefully instead of failing the whole page render.
    return fallback;
  }
}

export function getArticles(params: {
  category?: string;
  source?: string;
  sort?: "latest" | "hot" | "feed";
  page?: number;
  pageSize?: number;
}): Promise<ArticlePage> {
  const query = new URLSearchParams();
  if (params.category) query.set("category", params.category);
  if (params.source) query.set("source", params.source);
  if (params.sort) query.set("sort", params.sort);
  query.set("page", String(params.page ?? 1));
  query.set("page_size", String(params.pageSize ?? 20));

  return safeFetch<ArticlePage>(`/api/articles?${query.toString()}`, 120, {
    items: [],
    page: 1,
    page_size: params.pageSize ?? 20,
    total: 0,
    has_more: false,
  });
}

export function getCategories(): Promise<Category[]> {
  return safeFetch<Category[]>(`/api/categories`, 3600, []);
}

export function getSources(): Promise<Source[]> {
  return safeFetch<Source[]>(`/api/sources`, 3600, []);
}
