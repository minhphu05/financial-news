import { ArrowUpRight, Calendar, Tag } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Card, CardBody } from "@/components/ui/Card";
import { formatRelative, truncate } from "@/lib/utils";
import type { NewsArticle } from "@/types";

/**
 * Article preview card used by the news list. Renders the title, summary
 * (or the first ~200 chars of the cleaned body), the ticker badge, and the
 * publish/scrape timestamp. Clicking the card opens the original CafeF
 * article in a new tab.
 */
export function NewsCard({ article }: { article: NewsArticle }) {
  const preview = article.summary || truncate(article.clean_text ?? "", 220);

  return (
    <Card
      interactive
      role="article"
      className="overflow-hidden"
      onClick={() => window.open(article.link, "_blank", "noopener,noreferrer")}
    >
      <CardBody className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {article.ticker_symbol && (
            <Badge tone="brand" className="font-mono uppercase">
              <Tag size={11} className="opacity-80" />
              {article.ticker_symbol}
            </Badge>
          )}
          {article.source && (
            <Badge tone="muted">{article.source}</Badge>
          )}
          <span className="ml-auto inline-flex items-center gap-1.5 text-xs text-ink-400">
            <Calendar size={12} />
            {article.post_date || formatRelative(article.cleaned_at)}
          </span>
        </div>

        <h3 className="text-base font-semibold text-ink-50 leading-snug">
          {article.title || "(Không có tiêu đề)"}
        </h3>

        {preview && (
          <p className="text-sm text-ink-300 leading-relaxed line-clamp-3">
            {preview}
          </p>
        )}

        <div className="mt-1 flex items-center justify-between">
          <span className="text-xs text-ink-500 truncate max-w-[60%]">
            {article.link}
          </span>
          <span className="inline-flex items-center gap-1 text-xs text-brand-300">
            Đọc bài gốc
            <ArrowUpRight size={14} />
          </span>
        </div>
      </CardBody>
    </Card>
  );
}
