import { useQuery } from "@tanstack/react-query";

import { fetchStocks } from "@/api/stocks";

/**
 * React Query hook returning the VN50 catalogue.
 *
 * Article counts change when the daily ingestion runs, so the query is
 * cached for 5 minutes and re-fetched on window focus.
 */
export function useStocks(withCounts = true) {
  return useQuery({
    queryKey: ["stocks", withCounts] as const,
    queryFn: () => fetchStocks(withCounts),
    staleTime: 5 * 60_000,
  });
}
