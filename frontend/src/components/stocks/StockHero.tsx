import { Bot, FileText, Newspaper } from "lucide-react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import type { Stock } from "@/types";

/**
 * Hero banner used on top of the per-stock news page. Shows ticker, name,
 * sector, article count, and a quick-link to ask the chatbot about this
 * stock.
 */
export function StockHero({ stock }: { stock: Stock }) {
  return (
    <Card className="overflow-hidden">
      <CardBody className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="flex flex-col gap-2 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-3xl font-bold tracking-tight text-ink-50 font-mono">
              {stock.ticker}
            </h1>
            <Badge tone="brand">{stock.sector}</Badge>
          </div>
          <p className="text-ink-200 text-lg leading-snug">{stock.name_vi}</p>
          <p className="text-ink-500 text-sm">{stock.name_en}</p>
        </div>

        <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-center md:flex-col md:items-end">
          <div className="flex items-center gap-2 text-sm text-ink-300">
            <Newspaper size={16} className="text-brand-400" />
            <span>
              <span className="font-semibold text-ink-50">
                {stock.article_count}
              </span>{" "}
              bài đã lưu
            </span>
          </div>
          <Link to={`/chat?ticker=${stock.ticker}`}>
            <Button variant="primary" leftIcon={<Bot size={16} />}>
              Hỏi chatbot về {stock.ticker}
            </Button>
          </Link>
          <a
            href={`https://cafef.vn/tim-kiem/trang-1.chn?keywords=${stock.ticker}`}
            target="_blank"
            rel="noreferrer"
          >
            <Button variant="outline" leftIcon={<FileText size={16} />}>
              Mở CafeF
            </Button>
          </a>
        </div>
      </CardBody>
    </Card>
  );
}
