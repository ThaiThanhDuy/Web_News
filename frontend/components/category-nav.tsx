"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutGrid, type LucideIcon } from "lucide-react";

import { getCategoryMeta } from "@/lib/category-meta";
import { cn } from "@/lib/utils";
import type { Category } from "@/lib/types";

// Display order. "khac" (Khác, the catch-all) is always last.
const CATEGORY_ORDER = [
  "ai",
  "may-tinh",
  "phan-cung",
  "phan-mem",
  "di-dong",
  "game",
  "startup",
  "kinh-te",
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

/**
 * Category bar in the sticky header: a row of icon-only bubbles. A bubble
 * opens into a full pill (icon + name) on hover or keyboard focus; the
 * active category is always open, filled with its own gradient.
 */
export function CategoryNav({ categories }: { categories: Category[] }) {
  const pathname = usePathname();
  const visible = sortedVisibleCategories(categories);
  const navRef = useRef<HTMLElement>(null);

  // Keep the active pill in view when the row scrolls sideways (phones).
  useEffect(() => {
    const nav = navRef.current;
    const active = nav?.querySelector<HTMLElement>('[aria-current="page"]');
    if (!nav || !active) return;
    // Wait one frame so the pill has finished opening before measuring.
    const id = requestAnimationFrame(() => {
      const navBox = nav.getBoundingClientRect();
      const pillBox = active.getBoundingClientRect();
      const delta = pillBox.left + pillBox.width / 2 - (navBox.left + navBox.width / 2);
      nav.scrollTo({ left: nav.scrollLeft + delta, behavior: "smooth" });
    });
    return () => cancelAnimationFrame(id);
  }, [pathname]);

  const items = [
    {
      href: "/",
      label: "Tất cả",
      icon: LayoutGrid,
      iconClass: "text-primary",
      gradient: "from-primary to-secondary",
    },
    ...visible.map((category) => {
      const meta = getCategoryMeta(category.slug);
      return {
        href: `/category/${category.slug}`,
        label: category.name,
        icon: meta.icon,
        iconClass: meta.text,
        gradient: meta.gradient,
      };
    }),
  ];

  return (
    <nav
      ref={navRef}
      aria-label="Chuyên mục"
      // py gives the hover lift room inside the scroll container;
      // auto margins on the ends center the row when it fits without
      // clipping its start when it overflows.
      className="no-scrollbar flex items-center gap-1.5 overflow-x-auto px-1 py-1.5 [&>*:first-child]:ml-auto [&>*:last-child]:mr-auto"
    >
      {items.map((item, i) => (
        <CategoryBubble key={item.href} {...item} index={i} active={pathname === item.href} />
      ))}
    </nav>
  );
}

function CategoryBubble({
  href,
  label,
  icon: Icon,
  iconClass,
  gradient,
  active,
  index,
}: {
  href: string;
  label: string;
  icon: LucideIcon;
  iconClass: string;
  gradient: string;
  active: boolean;
  index: number;
}) {
  // Replays the "pop" each time this bubble becomes the active one.
  const [popKey, setPopKey] = useState(0);
  const wasActive = useRef(active);
  useEffect(() => {
    if (active && !wasActive.current) setPopKey((k) => k + 1);
    wasActive.current = active;
  }, [active]);

  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      style={{ animationDelay: `${index * 35}ms` }}
      className={cn(
        // No border and no shadow: flat bubbles, only the icon carries color.
        "group relative flex h-8 shrink-0 animate-bubble-in items-center rounded-full px-2 text-[0.8125rem] font-semibold",
        "outline-none transition-[background-color,color,transform] duration-300 ease-out",
        "focus-visible:ring-2 focus-visible:ring-primary/60",
        "motion-reduce:animate-none motion-reduce:transition-none",
        active
          ? cn("bg-gradient-to-br text-white", gradient)
          : "bg-foreground/[0.04] text-foreground/80 hover:bg-foreground/[0.08] hover:text-foreground dark:bg-foreground/[0.07] dark:hover:bg-foreground/[0.12]"
      )}
    >
      <span
        key={popKey}
        className={cn(
          "flex h-4 w-4 shrink-0 items-center justify-center transition-transform duration-300 ease-out",
          "group-hover:scale-110 group-hover:-rotate-6 motion-reduce:transform-none",
          active && "animate-pop"
        )}
      >
        <Icon className={cn("h-4 w-4", active ? "text-white" : iconClass)} />
      </span>
      {/* The label collapses to zero width; hover/focus (or being active)
          opens it, which turns the bubble into a pill. */}
      <span
        className={cn(
          "overflow-hidden whitespace-nowrap transition-[max-width,opacity,margin] duration-300 ease-out motion-reduce:transition-none",
          active
            ? "ml-1.5 mr-1 max-w-[10rem] opacity-100"
            : "ml-0 mr-0 max-w-0 opacity-0 group-hover:ml-1.5 group-hover:mr-1 group-hover:max-w-[10rem] group-hover:opacity-100 group-focus-visible:ml-1.5 group-focus-visible:mr-1 group-focus-visible:max-w-[10rem] group-focus-visible:opacity-100"
        )}
      >
        {label}
      </span>
    </Link>
  );
}
