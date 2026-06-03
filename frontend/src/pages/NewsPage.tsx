import { NewsList } from "@/components/news/NewsList";

/**
 * Generic news page. Lists every article in the corpus with search.
 */
export function NewsPage() {
  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold tracking-tight text-ink-50">
          Tin tức tài chính
        </h1>
        <p className="text-sm text-ink-400">
          Toàn bộ bài viết đã được thu thập, làm sạch và lưu trong MongoDB.
        </p>
      </header>
      <NewsList />
    </div>
  );
}
