import { Link, useParams } from "react-router-dom";
import { AlertTriangle, ArrowLeft } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { NewsList } from "@/components/news/NewsList";
import { StockHero } from "@/components/stocks/StockHero";
import { useStocks } from "@/hooks/useStocks";

/**
 * Per-stock news page. Reads the ``:ticker`` route param, looks up the
 * stock in the VN50 catalogue, and renders a hero + ``NewsList``.
 */
export function StockNewsPage() {
  const { ticker } = useParams<{ ticker: string }>();
  const symbol = ticker?.toUpperCase();

  const { data, isLoading, isError } = useStocks(true);
  const stock = data?.stocks.find((s) => s.ticker === symbol);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Spinner label="Đang tải dữ liệu cổ phiếu..." />
      </div>
    );
  }

  if (isError) {
    return (
      <EmptyState
        icon={<AlertTriangle size={28} />}
        title="Không tải được thông tin cổ phiếu"
        description="Kiểm tra FastAPI backend hoặc thử lại sau."
      />
    );
  }

  if (!symbol || !stock) {
    return (
      <EmptyState
        icon={<AlertTriangle size={28} />}
        title="Không tìm thấy mã cổ phiếu"
        description={`Mã "${symbol ?? ""}" không nằm trong danh mục VN50 của Financial News.`}
        action={
          <Link to="/">
            <Button variant="outline" leftIcon={<ArrowLeft size={14} />}>
              Quay lại trang chủ
            </Button>
          </Link>
        }
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <StockHero stock={stock} />
      <section className="flex flex-col gap-4">
        <header>
          <h2 className="text-lg font-semibold text-ink-50">
            Tin tức liên quan đến {stock.ticker}
          </h2>
          <p className="text-sm text-ink-400">
            Lọc tự động theo ticker, sắp xếp theo thời gian cập nhật.
          </p>
        </header>
        <NewsList ticker={symbol} />
      </section>
    </div>
  );
}
