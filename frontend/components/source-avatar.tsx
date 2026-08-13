"use client";

import { useState } from "react";

import type { Source } from "@/lib/types";

const SOURCE_COLORS: Record<string, string> = {
  vnexpress: "bg-blue-600",
  genk: "bg-orange-500",
  vietnamnet: "bg-emerald-600",
};

export function SourceAvatar({ source, size = 28 }: { source: Source; size?: number }) {
  const [imgError, setImgError] = useState(false);
  const color = SOURCE_COLORS[source.slug] ?? "bg-primary";

  if (imgError) {
    return (
      <span
        className={`flex shrink-0 items-center justify-center rounded-full text-xs font-bold text-white ${color}`}
        style={{ width: size, height: size }}
      >
        {source.name.charAt(0)}
      </span>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={source.logo_url}
      alt={source.name}
      width={size}
      height={size}
      className="shrink-0 rounded-full bg-white object-contain ring-1 ring-border"
      style={{ width: size, height: size }}
      onError={() => setImgError(true)}
    />
  );
}
