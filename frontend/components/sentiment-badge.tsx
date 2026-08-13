import { Minus, TrendingDown, TrendingUp } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { Sentiment } from "@/lib/types";

const CONFIG: Record<
  Sentiment,
  { label: string; variant: "positive" | "negative" | "neutral"; Icon: typeof TrendingUp; dot: string }
> = {
  positive: { label: "Tích cực", variant: "positive", Icon: TrendingUp, dot: "bg-positive" },
  negative: { label: "Tiêu cực", variant: "negative", Icon: TrendingDown, dot: "bg-negative" },
  neutral: { label: "Trung lập", variant: "neutral", Icon: Minus, dot: "bg-neutral" },
};

export function SentimentBadge({ sentiment }: { sentiment: Sentiment | null }) {
  if (!sentiment) return null;
  const { label, variant, Icon, dot } = CONFIG[sentiment];

  return (
    <Badge variant={variant} className="gap-1.5">
      <span className="relative flex h-1.5 w-1.5">
        <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-75 ${dot}`} />
        <span className={`relative inline-flex h-1.5 w-1.5 rounded-full ${dot}`} />
      </span>
      <Icon className="h-3 w-3" />
      {label}
    </Badge>
  );
}
