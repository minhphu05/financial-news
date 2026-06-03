import { Link } from "react-router-dom";
import { ArrowRight, Bot, Database, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { NewsList } from "@/components/news/NewsList";
import { StockGrid } from "@/components/stocks/StockGrid";
import { Spinner } from "@/components/ui/Spinner";
import { useStocks } from "@/hooks/useStocks";

/**
 * Landing page. Shows a hero, an overview of the VN50 catalogue, and the
 * latest news across the whole corpus.
 */
export function HomePage() {
  const { data, isLoading, isError } = useStocks(true);
  const total = data?.total ?? 0;
  const tracked = (data?.stocks ?? []).filter((s) => s.article_count > 0).length;
  const articles = (data?.stocks ?? []).reduce((acc, s) => acc + s.article_count, 0);

  return (
    <div className="flex flex-col gap-10">
      {/* HERO */}
      <section className="flex flex-col gap-6">
        <div className="flex flex-col gap-3">
          <Badge tone="brand" className="self-start">
            <Sparkles size={12} />
            Vietnamese financial news · RAG · Gemini
          </Badge>
          <h1 className="text-3xl font-bold tracking-tight text-ink-50 light:text-ink-900 sm:text-4xl">
            Tin tức tài chính VN50, được trợ giúp bởi AI.
          </h1>
          <p className="max-w-2xl text-base text-ink-300 light:text-ink-600 leading-relaxed">
            Financial News tự động thu thập tin tức từ CafeF, lưu vào MongoDB, vector-hoá
            bằng AI và phục vụ qua một chatbot biết trích nguồn. Khám phá theo
            mã VN50 hoặc trò chuyện trực tiếp với trợ lý AI.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link to="/chat">
              <Button variant="primary" leftIcon={<Bot size={16} />}>
                Trò chuyện với chatbot
              </Button>
            </Link>
            <Link to="/news">
              <Button variant="outline" rightIcon={<ArrowRight size={16} />}>
                Duyệt tin tức
              </Button>
            </Link>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <StatCard
            label="Mã VN50 đang theo dõi"
            value={total}
            hint="từ Financial News catalogue"
          />
          <StatCard
            label="Mã đã có dữ liệu"
            value={tracked}
            hint="có ít nhất 1 bài"
            tone="brand"
          />
          <StatCard
            label="Bài viết đã lưu"
            value={articles}
            hint="MongoDB cafef_clean"
            tone="brand"
          />
        </div>
      </section>

      {/* STOCK GRID */}
      <section className="flex flex-col gap-4">
        <header className="flex items-end justify-between">
          <div>
            <h2 className="text-lg font-semibold text-ink-50">
              Toàn bộ VN50
            </h2>
            <p className="text-sm text-ink-400">
              Chọn một mã để xem tin tức và hỏi chatbot.
            </p>
          </div>
        </header>
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <Spinner label="Đang tải danh sách cổ phiếu..." />
          </div>
        )}
        {isError && (
          <EmptyState
            icon={<Database size={28} />}
            title="Không tải được danh sách"
            description="Kiểm tra FastAPI backend (cổng 8000) đã sẵn sàng chưa."
          />
        )}
        {data && <StockGrid stocks={data.stocks} />}
      </section>

      {/* LATEST NEWS */}
      <section className="flex flex-col gap-4">
        <header className="flex items-end justify-between">
          <div>
            <h2 className="text-lg font-semibold text-ink-50">
              Tin tức mới nhất
            </h2>
            <p className="text-sm text-ink-400">
              Toàn bộ mã VN50, sắp xếp theo thời gian cập nhật.
            </p>
          </div>
          <Link to="/news">
            <Button variant="ghost" size="sm" rightIcon={<ArrowRight size={14} />}>
              Xem tất cả
            </Button>
          </Link>
        </header>
        <NewsList showSearch={false} />
      </section>
    </div>
  );
}

function StatCard({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: number;
  hint: string;
  tone?: "default" | "brand";
}) {
  return (
    <Card>
      <CardBody className="flex flex-col gap-1">
        <span className="text-xs uppercase tracking-wider text-ink-500">
          {label}
        </span>
        <span
          className={
            tone === "brand"
              ? "text-3xl font-bold text-brand-300"
              : "text-3xl font-bold text-ink-50"
          }
        >
          {value.toLocaleString("vi-VN")}
        </span>
        <span className="text-xs text-ink-400">{hint}</span>
      </CardBody>
    </Card>
  );
}
