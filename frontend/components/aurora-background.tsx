"use client";

import { useEffect, useState } from "react";

// Renders nothing on the server and on the first client render, then swaps
// in the real content after mount. This is purely decorative (fixed
// full-viewport overlay), so a one-frame delay is invisible — but it also
// means hydration never has to reconcile this subtree against whatever a
// browser extension may have already injected into it, which is what a
// `fixed inset-0` div like this one tends to attract (dark-mode/reader/
// ad-blocker overlays) and what was causing hydration-mismatch errors here.
export function AuroraBackground() {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return null;
  }

  return (
    <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
      <div className="animate-float-a absolute -left-32 -top-32 h-[28rem] w-[28rem] rounded-full bg-primary/25 blur-[110px]" />
      <div className="animate-float-b absolute -right-32 top-1/4 h-[28rem] w-[28rem] rounded-full bg-secondary/25 blur-[110px]" />
      <div className="animate-float-a absolute -bottom-40 left-1/3 h-[24rem] w-[24rem] rounded-full bg-flame/15 blur-[110px]" />
    </div>
  );
}
