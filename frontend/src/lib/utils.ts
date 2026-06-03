import clsx, { type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * `cn` (className) — merge any number of Tailwind class strings while
 * resolving conflicts (`twMerge`) and trimming falsy values (`clsx`).
 *
 * @example
 *   cn("px-2 py-1", isActive && "bg-brand-500", "px-4") // "py-1 bg-brand-500 px-4"
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/**
 * Format a date-like value into a short Vietnamese-friendly string.
 *
 * Accepts native `Date`, ISO strings, or `null`/`undefined`. Falls back to
 * the original string when it can't be parsed (CafeF post dates often look
 * like `"12-05-2026 09:30"` which the browser doesn't always understand).
 */
export function formatDate(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const date = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) {
    return typeof value === "string" ? value : "—";
  }
  return date.toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Compact relative time helper (e.g. "2 giờ trước"). Returns ``formatDate``
 * for anything older than 7 days.
 */
export function formatRelative(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const date = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return formatDate(value);

  const diffMs = Date.now() - date.getTime();
  const min = Math.round(diffMs / 60_000);
  if (min < 1) return "vừa xong";
  if (min < 60) return `${min} phút trước`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr} giờ trước`;
  const d = Math.round(hr / 24);
  if (d < 7) return `${d} ngày trước`;
  return formatDate(date);
}

/**
 * Truncate a string to ``max`` chars and add a trailing ellipsis.
 */
export function truncate(text: string | null | undefined, max = 160): string {
  if (!text) return "";
  return text.length <= max ? text : `${text.slice(0, max - 1)}…`;
}
