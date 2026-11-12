import {
  BrainCircuit,
  Cpu,
  FlaskConical,
  Gamepad2,
  Laptop,
  type LucideIcon,
  MoreHorizontal,
  Rocket,
  Share2,
  ShieldAlert,
  Smartphone,
  SquareCode,
  TrendingUp,
} from "lucide-react";

interface CategoryMeta {
  icon: LucideIcon;
  dot: string;
  text: string;
  ring: string;
  border: string;
  chip: string;
  gradientFrom: string;
  /** Full gradient (literal classes so Tailwind keeps them) for the active pill. */
  gradient: string;
  /** Colored glow (active topic chip in the search palette). */
  glow: string;
}

const DEFAULT_META: CategoryMeta = {
  icon: MoreHorizontal,
  dot: "bg-slate-400",
  text: "text-slate-500 dark:text-slate-400",
  ring: "ring-slate-400/30",
  border: "border-slate-400/50",
  chip: "bg-slate-500/10 text-slate-600 dark:text-slate-300",
  gradientFrom: "from-slate-400",
  gradient: "from-slate-400 to-slate-600",
  glow: "shadow-slate-500/30",
};

export const CATEGORY_META: Record<string, CategoryMeta> = {
  ai: {
    icon: BrainCircuit,
    dot: "bg-violet-500",
    text: "text-violet-600 dark:text-violet-400",
    ring: "ring-violet-500/30",
    border: "border-violet-500/60",
    chip: "bg-violet-500/10 text-violet-600 dark:text-violet-400",
    gradientFrom: "from-violet-500",
    gradient: "from-violet-500 to-fuchsia-500",
    glow: "shadow-violet-500/40",
  },
  "di-dong": {
    icon: Smartphone,
    dot: "bg-blue-500",
    text: "text-blue-600 dark:text-blue-400",
    ring: "ring-blue-500/30",
    border: "border-blue-500/60",
    chip: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
    gradientFrom: "from-blue-500",
    gradient: "from-blue-500 to-cyan-500",
    glow: "shadow-blue-500/40",
  },
  "may-tinh": {
    icon: Laptop,
    dot: "bg-indigo-500",
    text: "text-indigo-600 dark:text-indigo-400",
    ring: "ring-indigo-500/30",
    border: "border-indigo-500/60",
    chip: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400",
    gradientFrom: "from-indigo-500",
    gradient: "from-indigo-500 to-blue-500",
    glow: "shadow-indigo-500/40",
  },
  "phan-cung": {
    icon: Cpu,
    dot: "bg-slate-500",
    text: "text-slate-600 dark:text-slate-300",
    ring: "ring-slate-500/30",
    border: "border-slate-500/60",
    chip: "bg-slate-500/10 text-slate-600 dark:text-slate-300",
    gradientFrom: "from-slate-500",
    gradient: "from-slate-500 to-slate-700",
    glow: "shadow-slate-500/40",
  },
  "phan-mem": {
    icon: SquareCode,
    dot: "bg-cyan-500",
    text: "text-cyan-600 dark:text-cyan-400",
    ring: "ring-cyan-500/30",
    border: "border-cyan-500/60",
    chip: "bg-cyan-500/10 text-cyan-600 dark:text-cyan-400",
    gradientFrom: "from-cyan-500",
    gradient: "from-cyan-500 to-teal-500",
    glow: "shadow-cyan-500/40",
  },
  game: {
    icon: Gamepad2,
    dot: "bg-fuchsia-500",
    text: "text-fuchsia-600 dark:text-fuchsia-400",
    ring: "ring-fuchsia-500/30",
    border: "border-fuchsia-500/60",
    chip: "bg-fuchsia-500/10 text-fuchsia-600 dark:text-fuchsia-400",
    gradientFrom: "from-fuchsia-500",
    gradient: "from-fuchsia-500 to-pink-500",
    glow: "shadow-fuchsia-500/40",
  },
  startup: {
    icon: Rocket,
    dot: "bg-orange-500",
    text: "text-orange-600 dark:text-orange-400",
    ring: "ring-orange-500/30",
    border: "border-orange-500/60",
    chip: "bg-orange-500/10 text-orange-600 dark:text-orange-400",
    gradientFrom: "from-orange-500",
    gradient: "from-orange-500 to-amber-500",
    glow: "shadow-orange-500/40",
  },
  "kinh-te": {
    icon: TrendingUp,
    dot: "bg-amber-500",
    text: "text-amber-600 dark:text-amber-400",
    ring: "ring-amber-500/30",
    border: "border-amber-500/60",
    chip: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
    gradientFrom: "from-amber-500",
    gradient: "from-amber-500 to-yellow-500",
    glow: "shadow-amber-500/40",
  },
  "mang-xa-hoi": {
    icon: Share2,
    dot: "bg-pink-500",
    text: "text-pink-600 dark:text-pink-400",
    ring: "ring-pink-500/30",
    border: "border-pink-500/60",
    chip: "bg-pink-500/10 text-pink-600 dark:text-pink-400",
    gradientFrom: "from-pink-500",
    gradient: "from-pink-500 to-rose-500",
    glow: "shadow-pink-500/40",
  },
  "an-ninh-mang": {
    icon: ShieldAlert,
    dot: "bg-red-500",
    text: "text-red-600 dark:text-red-400",
    ring: "ring-red-500/30",
    border: "border-red-500/60",
    chip: "bg-red-500/10 text-red-600 dark:text-red-400",
    gradientFrom: "from-red-500",
    gradient: "from-red-500 to-orange-500",
    glow: "shadow-red-500/40",
  },
  "khoa-hoc": {
    icon: FlaskConical,
    dot: "bg-emerald-500",
    text: "text-emerald-600 dark:text-emerald-400",
    ring: "ring-emerald-500/30",
    border: "border-emerald-500/60",
    chip: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
    gradientFrom: "from-emerald-500",
    gradient: "from-emerald-500 to-teal-500",
    glow: "shadow-emerald-500/40",
  },
  khac: DEFAULT_META,
};

export function getCategoryMeta(slug: string | undefined | null): CategoryMeta {
  if (!slug) return DEFAULT_META;
  return CATEGORY_META[slug] ?? DEFAULT_META;
}
