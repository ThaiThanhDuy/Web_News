import Link from "next/link";
import { Sparkles } from "lucide-react";

import { CategoryNav } from "@/components/category-nav";
import { PushNotifications } from "@/components/push-notifications";
import { InstallButton } from "@/components/pwa";
import { ThemeToggle } from "@/components/theme-toggle";
import type { Category } from "@/lib/types";

export function Header({ categories }: { categories: Category[] }) {
  return (
    // The whole header — logo row + category row — is sticky, so the
    // categories stay reachable however far down the feed the reader is.
    <header className="sticky top-0 z-30 border-b border-border/60 bg-background/75 backdrop-blur-lg supports-[backdrop-filter]:bg-background/60">
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-primary/50 to-transparent" />
      <div className="container flex h-16 items-center justify-between gap-4">
        <Link href="/" className="group flex items-center gap-2.5">
          <span className="glass-sheen relative flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary via-primary to-secondary text-primary-foreground shadow-lg shadow-primary/30 transition-transform duration-300 group-hover:scale-110 group-hover:rotate-6">
            <span className="absolute inset-0 rounded-xl bg-gradient-to-br from-primary via-primary to-secondary opacity-0 blur-md transition-opacity duration-300 group-hover:opacity-70" />
            <Sparkles className="relative h-4 w-4" />
          </span>
          <div className="text-gradient text-lg font-extrabold tracking-tight">Tech Digest</div>
        </Link>

        <div className="flex items-center gap-3">
          <InstallButton />
          <PushNotifications categories={categories} />
          <ThemeToggle />
        </div>
      </div>

      {/* Full-width (not `container`) so all categories fit on one row on
          desktop; the faded edges hint that it scrolls on narrower screens. */}
      <div className="px-2 pb-2.5 [mask-image:linear-gradient(to_right,transparent,black_16px,black_calc(100%-16px),transparent)] sm:px-4">
        <CategoryNav
          categories={categories}
          layout="horizontal"
          // Auto margins on the first/last pill center the row when it fits,
          // without clipping its start when it overflows and scrolls.
          className="gap-1.5 pt-1 [&>*:first-child]:ml-auto [&>*:last-child]:mr-auto"
        />
      </div>
    </header>
  );
}
