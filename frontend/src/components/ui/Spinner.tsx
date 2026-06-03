import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Lightweight loading spinner. Defaults to brand colour.
 */
export function Spinner({
  className,
  size = 18,
  label,
}: {
  className?: string;
  size?: number;
  label?: string;
}) {
  return (
    <span
      role="status"
      aria-live="polite"
      className={cn("inline-flex items-center gap-2 text-brand-400", className)}
    >
      <Loader2 size={size} className="animate-spin" />
      {label && <span className="text-sm text-ink-300">{label}</span>}
    </span>
  );
}
