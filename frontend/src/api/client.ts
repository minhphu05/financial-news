import axios, { AxiosError, type AxiosInstance } from "axios";

/**
 * Centralised axios instance used by every API module.
 *
 * The base URL is resolved from `VITE_API_BASE_URL`. When unset (the
 * default for `vite dev`), the Vite dev server proxies `/api/*` to the
 * FastAPI backend (see `vite.config.ts`).
 */
const BASE_URL = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") || "/api";

export const apiClient: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 120_000,
  headers: { "Content-Type": "application/json" },
});

/**
 * Extract a human-readable error message from an axios failure.
 */
export function extractErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<{ detail?: string | { msg: string }[] }>;
    const detail = axiosError.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
    if (axiosError.message) return axiosError.message;
  }
  if (error instanceof Error) return error.message;
  return "Đã xảy ra lỗi không xác định.";
}
