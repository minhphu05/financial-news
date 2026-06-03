import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/**
 * Generic card surface used for articles, panels, and other elevated
 * content blocks. Renders a translucent glassy panel by default; pass
 * ``interactive`` to add a hover effect.
 */
export function Card({
  className,
  interactive = false,
  ...rest
}: HTMLAttributes<HTMLDivElement> & { interactive?: boolean }) {
  return (
    <div
      className={cn(
        "glass rounded-xl shadow-sm",
        interactive &&
          "transition-all duration-200 hover:border-brand-500/40 hover:shadow-glow cursor-pointer",
        className,
      )}
      {...rest}
    />
  );
}

export function CardHeader({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-5 border-b border-ink-800", className)} {...rest} />;
}

export function CardBody({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-5", className)} {...rest} />;
}

export function CardFooter({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("p-4 border-t border-ink-800 bg-ink-900/40", className)} {...rest} />
  );
}
