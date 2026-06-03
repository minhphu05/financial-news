import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Card, CardBody } from "@/components/ui/Card";
import type { Stock } from "@/types";

/**
 * Responsive grid that displays every VN50 ticker. Each tile links to the
 * per-stock news page.
 */
export function StockGrid({ stocks }: { stocks: Stock[] }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
      {stocks.map((s) => (
        <Link key={s.ticker} to={`/news/${s.ticker}`}>
          <Card interactive className="h-full">
            <CardBody className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="font-mono text-lg font-semibold text-ink-50">
                  {s.ticker}
                </span>
                <Badge tone={s.article_count > 0 ? "brand" : "muted"}>
                  {s.article_count}
                </Badge>
              </div>
              <p className="text-sm text-ink-200 line-clamp-2">{s.name_vi}</p>
              <p className="text-[11px] text-ink-500 uppercase tracking-wide">
                {s.sector}
              </p>
            </CardBody>
          </Card>
        </Link>
      ))}
    </div>
  );
}
