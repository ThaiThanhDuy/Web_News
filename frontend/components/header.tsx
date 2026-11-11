import Link from "next/link";
import { Sparkles } from "lucide-react";

import { CategoryNav } from "@/components/category-nav";
import { PushNotifications } from "@/components/push-notifications";
import { InstallButton } from "@/components/pwa";
import { SearchLauncher } from "@/components/search-palette";
import { SettingsMenu } from "@/components/settings-menu";
import { ThemeToggle } from "@/components/theme-toggle";
import type { Category } from "@/lib/types";

export function Header({ categories }: { categories: Category[] }) {
  return (
    // Sticky (logo row + category row), solid background — no blur, no glow.
    <header className="sticky top-0 z-30 border-b border-border bg-background">
      {/* md+: the two outer columns share the leftover width equally
          (flex-1 basis-0), keeping the search box exactly centered.
          Phones: logo left, search icon + actions right. */}
      <div className="container flex h-12 items-center gap-2 sm:gap-4">
        <div className="flex md:flex-1 md:basis-0">
          <Link href="/" className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-secondary text-primary-foreground">
              <Sparkles className="h-3.5 w-3.5" />
            </span>
            <span className="text-base font-bold tracking-tight">Tech Digest</span>
          </Link>
        </div>

        <div className="ml-auto md:ml-0">
          <SearchLauncher />
        </div>

        <div className="flex items-center gap-1 md:flex-1 md:basis-0 md:justify-end">
          <InstallButton />
          <PushNotifications categories={categories} />
          <ThemeToggle />
          <SettingsMenu />
        </div>
      </div>

      {/* Faded edges hint that the bubble row scrolls on narrow screens. */}
      <div className="px-2 [mask-image:linear-gradient(to_right,transparent,black_16px,black_calc(100%-16px),transparent)] sm:px-4">
        <CategoryNav categories={categories} />
      </div>
    </header>
  );
}
