import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * Standardised "no data" placeholder used by lists and chat panes.
 */
export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center py-12 px-6 gap-3",
        "rounded-xl border border-dashed border-ink-800 bg-ink-900/40",
        className,
      )}
    >
      {icon && <div className="text-ink-500">{icon}</div>}
      <h3 className="text-base font-semibold text-ink-100">{title}</h3>
      {description && (
        <p className="text-sm text-ink-400 max-w-md leading-relaxed">{description}</p>
      )}
      {action}
    </div>
  );
}
