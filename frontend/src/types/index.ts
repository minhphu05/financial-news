/**
 * Shared TypeScript types mirroring the FastAPI Pydantic schemas in
 * `src/rag/api/schemas.py`.
 */

export interface Stock {
  ticker: string;
  name_vi: string;
  name_en: string;
  sector: string;
  article_count: number;
}

export interface StockListResponse {
  stocks: Stock[];
  total: number;
}

export interface NewsArticle {
  link: string;
  title?: string | null;
  post_date?: string | null;
  summary?: string | null;
  clean_text?: string | null;
  ticker_symbol?: string | null;
  ticker_name?: string | null;
  keyword?: string | null;
  source?: string | null;
  char_count?: number | null;
  cleaned_at?: string | null;
  embedded_at?: string | null;
}

export interface NewsListResponse {
  items: NewsArticle[];
  total: number;
  skip: number;
  limit: number;
}

export interface Citation {
  index: number;
  score: number;
  article_link: string;
  title?: string | null;
  post_date?: string | null;
  ticker_symbol?: string | null;
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
  model: string;
  cache_hit: boolean;
  cache_score?: number | null;
  latency_ms?: number | null;
}

export interface ChatRequest {
  question: string;
  model?: string;
  top_k?: number;
  score_threshold?: number;
  filters?: Record<string, string | number | boolean>;
}

export interface ModelsResponse {
  models: string[];
  default: string;
}

export type ChatRole = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  citations?: Citation[];
  model?: string;
  createdAt: number;
  pending?: boolean;
  error?: string;
}

export interface HealthResponse {
  status: string;
  mongo_raw: number;
  mongo_clean: number;
  mongo_embedded: number;
  qdrant_chunks: number;
}
