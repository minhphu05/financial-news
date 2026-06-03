import { apiClient } from "./client";
import type { NewsArticle, NewsListResponse } from "@/types";

export interface ListNewsParams {
  ticker?: string;
  search?: string;
  skip?: number;
  limit?: number;
}

/**
 * Fetch a page of cleaned articles.
 *
 * @param params Query options. ``ticker`` filters by ticker, ``search``
 *   does a case-insensitive title match.
 */
export async function fetchNews(params: ListNewsParams = {}): Promise<NewsListResponse> {
  const { data } = await apiClient.get<NewsListResponse>("/news", {
    params: {
      ticker: params.ticker || undefined,
      search: params.search || undefined,
      skip: params.skip ?? 0,
      limit: params.limit ?? 20,
    },
  });
  return data;
}

/**
 * Fetch a single article by its URL.
 */
export async function fetchNewsByLink(link: string): Promise<NewsArticle> {
  const { data } = await apiClient.get<NewsArticle>("/news/by-link", {
    params: { link },
  });
  return data;
}
