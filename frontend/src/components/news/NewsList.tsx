import { useState } from "react";
import { Newspaper, Search } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input } from "@/components/ui/Input";
import { Spinner } from "@/components/ui/Spinner";
import { useNews } from "@/hooks/useNews";

import { NewsCard } from "./NewsCard";

const PAGE_SIZE = 12;

interface NewsListProps {
  ticker?: string;
  initialSearch?: string;
  showSearch?: boolean;
}

/**
 * Paginated, searchable list of news articles. ``ticker`` is optional —
 * when omitted, the list shows the latest articles across the corpus.
 */
export function NewsList({ ticker, initialSearch = "", showSearch = true }: NewsListProps) {
  const [search, setSearch] = useState(initialSearch);
  const [searchDraft, setSearchDraft] = useState(initialSearch);
  const [page, setPage] = useState(0);

  const { data, isLoading, isFetching, isError } = useNews({
    ticker,
    search,
    skip: page * PAGE_SIZE,
    limit: PAGE_SIZE,
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const lastPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1);

  const submitSearch = () => {
    setPage(0);
    setSearch(searchDraft.trim());
  };

  return (
    <div className="flex flex-col gap-4">
      {showSearch && (
        <div className="flex flex-col sm:flex-row gap-2">
          <Input
            placeholder="Tìm theo tiêu đề bài viết..."
            leftIcon={<Search size={14} />}
            value={searchDraft}
            onChange={(e) => setSearchDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submitSearch();
            }}
            className="flex-1"
          />
          <Button variant="primary" onClick={submitSearch}>
            Tìm kiếm
          </Button>
        </div>
      )}

      {isLoading && (
        <div className="flex items-center justify-center py-16">
          <Spinner label="Đang tải tin tức..." />
        </div>
      )}

      {isError && (
        <EmptyState
          icon={<Newspaper size={28} />}
          title="Không tải được tin tức"
          description="Kiểm tra API backend (FastAPI) có đang chạy không, hoặc thử lại sau."
        />
      )}

      {!isLoading && !isError && items.length === 0 && (
        <EmptyState
          icon={<Newspaper size={28} />}
          title="Chưa có bài viết nào"
          description={
            ticker
              ? `Chưa có bài viết nào cho mã ${ticker}. Hãy chạy pipeline scrape + ingest để cập nhật.`
              : "Kho dữ liệu đang trống. Hãy chạy pipeline scrape + ingest để bổ sung dữ liệu."
          }
        />
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-2">
        {items.map((article) => (
          <NewsCard key={article.link} article={article} />
        ))}
      </div>

      {total > PAGE_SIZE && (
        <div className="mt-4 flex items-center justify-between text-sm">
          <span className="text-ink-400">
            Trang <span className="text-ink-100 font-medium">{page + 1}</span> /
            {" "}
            {lastPage + 1} · {total} bài
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page === 0 || isFetching}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
            >
              Trang trước
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= lastPage || isFetching}
              onClick={() => setPage((p) => Math.min(lastPage, p + 1))}
            >
              Trang sau
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
