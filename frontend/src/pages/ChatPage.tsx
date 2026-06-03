import { useSearchParams } from "react-router-dom";

import { ChatWindow } from "@/components/chat/ChatWindow";

/**
 * Full-page chat. Reads an optional ``?ticker=BCM`` query param so
 * navigating from the stock page pre-filters the chatbot's retrieval.
 */
export function ChatPage() {
  const [params] = useSearchParams();
  const ticker = params.get("ticker") || undefined;

  const suggestions = ticker
    ? [
        `Tóm tắt tin tức mới nhất về ${ticker}.`,
        `Có thông tin nào về kết quả kinh doanh của ${ticker}?`,
        `${ticker} có công bố hoạt động gì đáng chú ý?`,
        `So sánh ${ticker} với ngành.`,
      ]
    : undefined;

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold tracking-tight text-ink-50 light:text-ink-900">
          Trò chuyện với chatbot
          {ticker && <span className="ml-2 font-mono text-brand-300">· {ticker}</span>}
        </h1>
        <p className="text-sm text-ink-400 light:text-ink-600">
          Hỏi đáp về tin tức tài chính bằng tiếng Việt. Mọi câu trả lời đều
          kèm trích nguồn từ kho dữ liệu CafeF.
        </p>
      </header>
      <ChatWindow ticker={ticker} suggestions={suggestions} />
    </div>
  );
}
