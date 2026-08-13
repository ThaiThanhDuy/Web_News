import Link from "next/link";
import { Sparkles } from "lucide-react";

import { ThemeToggle } from "@/components/theme-toggle";

export function Header() {
  return (
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
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
