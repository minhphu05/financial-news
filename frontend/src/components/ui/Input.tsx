import { forwardRef, type InputHTMLAttributes, type ReactNode } from "react";

import { cn } from "@/lib/utils";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  leftIcon?: ReactNode;
  rightSlot?: ReactNode;
}

/**
 * Styled text input. Optional ``leftIcon`` and ``rightSlot`` are rendered
 * inside the input shell so the focus ring covers the whole control.
 */
export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, leftIcon, rightSlot, disabled, ...rest }, ref) => {
    return (
      <div
        className={cn(
          "group flex items-center gap-2 rounded-lg border border-ink-800 bg-ink-900/60",
          "focus-within:border-brand-500/50 focus-within:ring-1 focus-within:ring-brand-500/30",
          "transition-colors px-3 h-10",
          disabled && "opacity-50 pointer-events-none",
          className,
        )}
      >
        {leftIcon && <span className="text-ink-400">{leftIcon}</span>}
        <input
          ref={ref}
          className={cn(
            "flex-1 bg-transparent outline-none text-sm text-ink-100 placeholder:text-ink-500",
          )}
          disabled={disabled}
          {...rest}
        />
        {rightSlot}
      </div>
    );
  },
);
Input.displayName = "Input";
