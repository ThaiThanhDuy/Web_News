import { ArrowUpRight, Flame, Play } from "lucide-react";

import { ArticleThumbnail } from "@/components/article-thumbnail";
import { SentimentBadge } from "@/components/sentiment-badge";
import { SourceAvatar } from "@/components/source-avatar";
import { getCategoryMeta } from "@/lib/category-meta";
import { relativeTimeVi } from "@/lib/time";
import { cn } from "@/lib/utils";
import type { Article } from "@/lib/types";

export function FeedPost({ article, priority = false }: { article: Article; priority?: boolean }) {
  const meta = getCategoryMeta(article.category?.slug);
  const CategoryIcon = meta.icon;
  const isVideo = article.source.slug.startsWith("yt-");

  return (
    <article className="glass-card group relative overflow-hidden rounded-2xl p-5 shadow-lg shadow-black/[0.03] transition-all duration-300 hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 dark:shadow-black/20">
      <span className={cn("absolute inset-x-0 top-0 h-[3px] bg-gradient-to-r opacity-80 to-transparent", meta.gradientFrom)} />

      <div className="mb-2.5 flex items-center gap-2">
        <SourceAvatar source={article.source} />
        <div className="min-w-0 flex-1 leading-tight">
          <div className="truncate text-sm font-semibold text-foreground">{article.source.name}</div>
          <div className="text-xs text-muted-foreground">{relativeTimeVi(article.published_at)}</div>
        </div>
        {article.category && (
          <span className={cn("inline-flex shrink-0 items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold", meta.chip)}>
            <CategoryIcon className="h-3.5 w-3.5" />
            {article.category.name}
          </span>
        )}
      </div>

      <a href={article.original_url} target="_blank" rel="noopener noreferrer" className="text-foreground">
        <h2 className="mb-1.5 text-[17px] font-bold leading-snug underline decoration-primary/0 decoration-2 underline-offset-4 transition-colors duration-300 hover:text-primary hover:decoration-primary/60">
          {article.title}
        </h2>
      </a>

      {article.one_line_takeaway && (
        <p className="mb-2 border-l-2 border-primary/40 pl-2.5 text-sm italic text-muted-foreground">
          “{article.one_line_takeaway}”
        </p>
      )}

      {article.summary_bullets && article.summary_bullets.length > 0 && (
        <ul className="mb-3 space-y-1 text-sm text-foreground/85">
          {article.summary_bullets.map((bullet, i) => (
            <li key={i} className="flex gap-2">
              <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-gradient-to-br from-primary to-secondary" />
              <span>{bullet}</span>
            </li>
          ))}
        </ul>
      )}

      <a
        href={article.original_url}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={`${isVideo ? "Xem video" : "Đọc bài gốc"}: ${article.title}`}
        className="relative mb-3 block aspect-[16/9] w-full overflow-hidden rounded-xl bg-muted shadow-sm ring-1 ring-border/60 transition-all duration-500 group-hover:shadow-2xl group-hover:shadow-primary/20 group-hover:ring-primary/30"
      >
        <ArticleThumbnail src={article.thumbnail_url} alt={article.title} priority={priority} />
        <span className="pointer-events-none absolute inset-0 -translate-x-full skew-x-12 bg-gradient-to-r from-transparent via-white/20 to-transparent transition-transform duration-1000 ease-out group-hover:translate-x-full" />
        {isVideo && (
          <span className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <span className="flex h-14 w-14 items-center justify-center rounded-full bg-black/50 text-white shadow-lg backdrop-blur-sm transition-transform duration-300 group-hover:scale-110">
              <Play className="ml-1 h-6 w-6 fill-white" />
            </span>
          </span>
        )}
        {article.cross_source_count > 1 && (
          <span className="animate-glow-pulse absolute bottom-2.5 left-2.5 inline-flex items-center gap-1 rounded-full bg-flame px-2 py-1 text-[11px] font-semibold text-flame-foreground shadow-sm">
            <Flame className="h-3 w-3" />
            {article.cross_source_count} nguồn cùng đưa tin
          </span>
        )}
      </a>

      {article.keywords && article.keywords.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {article.keywords.slice(0, 5).map((kw) => (
            <span
              key={kw}
              className={cn(
                "rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors",
                meta.chip
              )}
            >
              #{kw}
            </span>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between gap-2 border-t border-border pt-3">
        <SentimentBadge sentiment={article.sentiment} />
        <a
          href={article.original_url}
          target="_blank"
          rel="noopener noreferrer"
          className="glass-sheen relative inline-flex shrink-0 items-center gap-1 rounded-full bg-gradient-to-r from-primary to-secondary px-3 py-1.5 text-xs font-semibold text-primary-foreground shadow-md shadow-primary/25 transition-all duration-300 hover:shadow-lg hover:shadow-primary/40 hover:brightness-110"
        >
          {isVideo ? "Xem video" : "Đọc bài gốc"}
          <ArrowUpRight className="h-3.5 w-3.5 transition-transform duration-300 group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
        </a>
      </div>
    </article>
  );
}
