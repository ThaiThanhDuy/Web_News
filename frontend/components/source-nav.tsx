"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Newspaper } from "lucide-react";

import { SourceAvatar } from "@/components/source-avatar";
import { cn } from "@/lib/utils";
import type { Source } from "@/lib/types";

// Video sources use this slug prefix (see backend VIDEO_SOURCE_SLUGS) — used
// here purely to group the panel into "Báo" vs "YouTube", not to hide anything.
function isVideoSource(source: Source): boolean {
  return source.slug.startsWith("yt-");
}

export function SourceNav({
  sources,
  layout,
  className,
}: {
  sources: Source[];
  layout: "vertical" | "horizontal";
  className?: string;
}) {
  const pathname = usePathname();
  const isAllActive = !pathname.startsWith("/source/");

  const articleSources = sources.filter((s) => !isVideoSource(s));
  const videoSources = sources.filter(isVideoSource);

  return (
    <nav
      className={cn(
        layout === "vertical"
          ? "flex flex-col gap-1"
          : "no-scrollbar flex gap-2 overflow-x-auto scroll-smooth pb-1",
        className
      )}
    >
      <SourceItem href="/" active={isAllActive} label="Tất cả nguồn" layout={layout} />

      {layout === "vertical" && articleSources.length > 0 && <GroupLabel>Báo</GroupLabel>}
      {articleSources.map((source) => {
        const href = `/source/${source.slug}`;
        return (
          <SourceItem
            key={source.slug}
            href={href}
            active={pathname === href}
            label={source.name}
            source={source}
            layout={layout}
          />
        );
      })}

      {layout === "vertical" && videoSources.length > 0 && <GroupLabel>YouTube</GroupLabel>}
      {videoSources.map((source) => {
        const href = `/source/${source.slug}`;
        return (
          <SourceItem
            key={source.slug}
            href={href}
            active={pathname === href}
            label={source.name}
            source={source}
            layout={layout}
          />
        );
      })}
    </nav>
  );
}

function GroupLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-3 pb-1 pt-3 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground/70">
      {children}
    </div>
  );
}

function SourceItem({
  href,
  active,
  label,
  source,
  layout,
}: {
  href: string;
  active: boolean;
  label: string;
  source?: Source;
  layout: "vertical" | "horizontal";
}) {
  return (
    <Link
      href={href}
      className={cn(
        "flex items-center gap-2 text-sm font-medium transition-all duration-300",
        layout === "vertical" ? "w-full rounded-lg px-3 py-2" : "shrink-0 rounded-full border px-3 py-1.5",
        layout === "vertical" &&
          (active
            ? "bg-gradient-to-r from-primary/15 to-secondary/10 text-primary shadow-sm ring-1 ring-primary/20"
            : "text-muted-foreground hover:translate-x-0.5 hover:bg-muted hover:text-foreground"),
        layout === "horizontal" &&
          (active
            ? "glass-sheen border-transparent bg-gradient-to-r from-primary to-secondary text-primary-foreground shadow-md shadow-primary/25"
            : "border-border bg-card text-muted-foreground hover:-translate-y-0.5 hover:border-primary/40 hover:text-foreground hover:shadow-sm")
      )}
    >
      {source ? (
        <SourceAvatar source={source} size={20} />
      ) : (
        <span
          className={cn(
            "flex h-5 w-5 shrink-0 items-center justify-center rounded-full transition-colors",
            active && layout === "vertical" ? "bg-primary/20" : "bg-accent"
          )}
        >
          <Newspaper className={cn("h-3 w-3", active && layout === "horizontal" ? "text-primary-foreground" : "text-primary")} />
        </span>
      )}
      <span className="whitespace-nowrap">{label}</span>
    </Link>
  );
}
