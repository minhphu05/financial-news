import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

type Tone = "default" | "brand" | "info" | "warning" | "danger" | "muted";

const TONES: Record<Tone, string> = {
  default: "bg-ink-800 text-ink-200 border-ink-700",
  brand: "bg-brand-500/10 text-brand-300 border-brand-500/30",
  info: "bg-sky-500/10 text-sky-300 border-sky-500/30",
  warning: "bg-amber-500/10 text-amber-300 border-amber-500/30",
  danger: "bg-rose-500/10 text-rose-300 border-rose-500/30",
  muted: "bg-ink-900 text-ink-400 border-ink-800",
};

/**
 * Small status pill used for tickers, scores, and metadata.
 */
export function Badge({
  tone = "default",
  className,
  ...rest
}: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium",
        TONES[tone],
        className,
      )}
      {...rest}
    />
  );
}
