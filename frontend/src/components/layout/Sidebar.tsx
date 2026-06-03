import { useMemo, useState } from "react";
import { NavLink } from "react-router-dom";
import { Filter, Search, X } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { Spinner } from "@/components/ui/Spinner";
import { useStocks } from "@/hooks/useStocks";
import { cn } from "@/lib/utils";

/**
 * Vertical sidebar that lists every VN50 ticker. Clicking a ticker routes
 * the user to ``/news/<ticker>``. A search box on top filters the list by
 * ticker or company name.
 */
export function Sidebar() {
  const { data, isLoading, isError } = useStocks(true);
  const [query, setQuery] = useState("");

  const stocks = data?.stocks ?? [];

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return stocks;
    return stocks.filter(
      (s) =>
        s.ticker.toLowerCase().includes(q) ||
        s.name_vi.toLowerCase().includes(q) ||
        s.name_en.toLowerCase().includes(q) ||
        s.sector.toLowerCase().includes(q),
    );
  }, [stocks, query]);

  return (
    <aside
      className={cn(
        "glass rounded-xl flex flex-col overflow-hidden",
        "h-[calc(100vh-6rem)] sticky top-20",
      )}
    >
      <div className="p-4 border-b border-ink-800 light:border-ink-200 flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ink-100 light:text-ink-800 inline-flex items-center gap-2">
            <Filter size={15} className="text-brand-400" />
            Mã cổ phiếu VN50
          </h2>
          {data && (
            <Badge tone="muted" className="font-mono">
              {data.total}
            </Badge>
          )}
        </div>
        <Input
          placeholder="Tìm theo mã, tên, ngành..."
          leftIcon={<Search size={14} />}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          rightSlot={
            query ? (
              <button
                type="button"
                aria-label="Xoá tìm kiếm"
                onClick={() => setQuery("")}
                className="text-ink-500 hover:text-ink-200"
              >
                <X size={14} />
              </button>
            ) : null
          }
        />
      </div>

      <nav className="flex-1 overflow-y-auto scroll-thin p-2">
        {isLoading && (
          <div className="flex items-center justify-center py-10">
            <Spinner label="Đang tải danh sách..." />
          </div>
        )}
        {isError && (
          <p className="px-3 py-6 text-sm text-rose-300">
            Không tải được danh sách cổ phiếu. Kiểm tra backend.
          </p>
        )}

        <ul className="space-y-1">
          {filtered.map((s) => (
            <li key={s.ticker}>
              <NavLink
                to={`/news/${s.ticker}`}
                className={({ isActive }) =>
                  cn(
                    "group flex items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm transition-colors",
                    isActive
                      ? "bg-brand-500/10 text-brand-200 ring-1 ring-brand-500/30 light:text-brand-700"
                      : "text-ink-200 hover:bg-ink-800/60 light:text-ink-700 light:hover:bg-ink-100",
                  )
                }
              >
                <div className="flex flex-col min-w-0">
                  <span className="font-semibold tracking-wide">{s.ticker}</span>
                  <span className="text-[11px] text-ink-400 truncate">{s.name_vi}</span>
                </div>
                <Badge
                  tone={s.article_count > 0 ? "brand" : "muted"}
                  className="font-mono"
                >
                  {s.article_count}
                </Badge>
              </NavLink>
            </li>
          ))}
          {!isLoading && filtered.length === 0 && (
            <li className="px-3 py-6 text-center text-sm text-ink-500">
              Không có mã nào khớp.
            </li>
          )}
        </ul>
      </nav>
    </aside>
  );
}
