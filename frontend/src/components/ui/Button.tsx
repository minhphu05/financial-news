import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "outline" | "danger";
type Size = "sm" | "md" | "lg" | "icon";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-brand-500 text-ink-950 hover:bg-brand-400 focus-visible:ring-brand-300 shadow-glow",
  secondary:
    "bg-ink-800 text-ink-100 hover:bg-ink-700 focus-visible:ring-ink-500 border border-ink-700",
  outline:
    "bg-transparent border border-ink-700 hover:border-brand-500/70 hover:text-brand-300 text-ink-100",
  ghost:
    "bg-transparent text-ink-200 hover:bg-ink-800/80 hover:text-ink-100",
  danger:
    "bg-rose-600 text-white hover:bg-rose-500 focus-visible:ring-rose-300",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-xs",
  md: "h-10 px-4 text-sm",
  lg: "h-12 px-5 text-base",
  icon: "h-9 w-9 p-0",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
}

/**
 * Primary clickable button used across the app.
 *
 * @example
 *   <Button variant="primary" leftIcon={<Send size={16} />}>Gửi</Button>
 */
export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  leftIcon,
  rightIcon,
  className,
  children,
  disabled,
  ...rest
}: ButtonProps) {
  const isDisabled = disabled || loading;
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium",
        "transition-all duration-150 outline-none",
        "focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-ink-950",
        "disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      disabled={isDisabled}
      {...rest}
    >
      {loading ? <Loader2 size={16} className="animate-spin" /> : leftIcon}
      {children}
      {rightIcon}
    </button>
  );
}
