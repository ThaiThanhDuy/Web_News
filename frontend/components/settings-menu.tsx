"use client";

import { useEffect, useRef, useState } from "react";
import { Settings } from "lucide-react";

import { headerIconButton } from "@/lib/ui";
import { cn } from "@/lib/utils";

/** Gear button + settings popup (same placement/behavior as the
 *  notifications popup). Intentionally empty for now — add sections inside
 *  the body below. */
export function SettingsMenu() {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  // Close on outside click / Escape.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(headerIconButton, open && "bg-muted text-foreground")}
        aria-label="Cài đặt"
        title="Cài đặt"
        aria-haspopup="dialog"
        aria-expanded={open}
      >
        <Settings
          className={cn(
            "h-4 w-4 transition-transform duration-300 ease-out motion-reduce:transition-none",
            open && "rotate-90"
          )}
        />
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Cài đặt"
          className="absolute right-0 top-10 z-40 w-[min(20rem,calc(100vw-2rem))] animate-palette-in rounded-2xl border border-border bg-background p-4 shadow-xl motion-reduce:animate-none"
        >
          <div className="text-sm font-bold">Cài đặt</div>
          {/* Settings sections go here. */}
          <div className="mt-3 min-h-[6rem]" />
        </div>
      )}
    </div>
  );
}
