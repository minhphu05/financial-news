import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { fetchNews, fetchNewsByLink, type ListNewsParams } from "@/api/news";

/**
 * Hook returning a page of news articles, optionally filtered.
 */
export function useNews(params: ListNewsParams) {
  return useQuery({
    queryKey: ["news", params] as const,
    queryFn: () => fetchNews(params),
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });
}

/**
 * Hook returning a single article by URL.
 */
export function useArticle(link: string | undefined) {
  return useQuery({
    queryKey: ["article", link] as const,
    queryFn: () => fetchNewsByLink(link as string),
    enabled: Boolean(link),
  });
}
