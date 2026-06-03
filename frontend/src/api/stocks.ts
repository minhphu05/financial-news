import { apiClient } from "./client";
import type { StockListResponse } from "@/types";

/**
 * Fetch the VN50 catalogue from the backend.
 *
 * @param withCounts When ``true`` (default) the response includes the
 *   number of stored articles per ticker.
 */
export async function fetchStocks(withCounts = true): Promise<StockListResponse> {
  const { data } = await apiClient.get<StockListResponse>("/stocks", {
    params: { with_counts: withCounts },
  });
  return data;
}
