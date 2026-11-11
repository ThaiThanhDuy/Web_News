"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutGrid, type LucideIcon } from "lucide-react";

import { getCategoryMeta } from "@/lib/category-meta";
import { cn } from "@/lib/utils";
import type { Category } from "@/lib/types";

// Display order for the category panel. "khac" (Khác, the catch-all) is
// always last, after every named category.
const CATEGORY_ORDER = [
  "ai",
  "may-tinh",
  "phan-cung",
  "phan-mem",
  "di-dong",
  "game",
  "startup",
  "mang-xa-hoi",
  "an-ninh-mang",
  "khoa-hoc",
  "khac",
];

function sortedVisibleCategories(categories: Category[]): Category[] {
  return [...categories]
    .filter((c) => CATEGORY_ORDER.includes(c.slug))
    .sort((a, b) => CATEGORY_ORDER.indexOf(a.slug) - CATEGORY_ORDER.indexOf(b.slug));
}

export function CategoryNav({
  categories,
  layout,
  className,
}: {
  categories: Category[];
  layout: "vertical" | "horizontal";
  className?: string;
}) {
  const pathname = usePathname();
  const visible = sortedVisibleCategories(categories);
  const navRef = useRef<HTMLElement>(null);

  // On narrow screens the horizontal bar scrolls sideways — keep the active
  // pill in view (e.g. after opening "Khoa học" from a link).
  useEffect(() => {
    if (layout !== "horizontal") return;
    const nav = navRef.current;
    const active = nav?.querySelector<HTMLElement>('[aria-current="page"]');
    if (!nav || !active) return;
    // Set scrollLeft directly (not scrollIntoView): it never scrolls the page
    // vertically, and isn't animated/deferred by the nav's scroll-smooth.
    const navBox = nav.getBoundingClientRect();
    const pillBox = active.getBoundingClientRect();
    const delta = pillBox.left + pillBox.width / 2 - (navBox.left + navBox.width / 2);
    nav.style.scrollBehavior = "auto";
    nav.scrollLeft += delta;
    nav.style.scrollBehavior = "";
  }, [pathname, layout]);

  return (
    <nav
      ref={navRef}
      aria-label="Chuyên mục"
      className={cn(
        layout === "vertical"
          ? "flex flex-col gap-1"
          : "no-scrollbar flex gap-2 overflow-x-auto scroll-smooth pb-1",
        className
      )}
    >
      <CategoryItem href="/" active={pathname === "/"} icon={LayoutGrid} label="Tất cả" layout={layout} iconClass="text-primary" />
      {visible.map((category) => {
        const href = `/category/${category.slug}`;
        const meta = getCategoryMeta(category.slug);
        return (
          <CategoryItem
            key={category.slug}
            href={href}
            active={pathname === href}
            icon={meta.icon}
            label={category.name}
            layout={layout}
            iconClass={meta.text}
          />
        );
      })}
    </nav>
  );
}

function CategoryItem({
  href,
  active,
  icon: Icon,
  label,
  layout,
  iconClass,
}: {
  href: string;
  active: boolean;
  icon: LucideIcon;
  label: string;
  layout: "vertical" | "horizontal";
  iconClass: string;
}) {
  // Vertical (sidebar) active state uses a soft tinted background, so the
  // icon stays in its own category color; horizontal (mobile pill) active
  // state is a solid gradient fill, so the icon needs to flip to white.
  const iconColorClass = !active ? iconClass : layout === "vertical" ? "text-primary" : "text-primary-foreground";

  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex items-center gap-2 text-sm font-medium transition-all duration-300",
        layout === "vertical"
          ? "w-full rounded-lg px-3 py-2"
          : "shrink-0 gap-1.5 rounded-full border px-2.5 py-1 text-[13px]",
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
      <span
        className={cn(
          "flex h-5 w-5 shrink-0 items-center justify-center rounded-full transition-colors",
          layout === "vertical" && (active ? "bg-primary/20" : "bg-accent")
        )}
      >
        <Icon className={cn("h-3.5 w-3.5 transition-transform duration-300", iconColorClass)} />
      </span>
      <span className="whitespace-nowrap">{label}</span>
    </Link>
  );
}
