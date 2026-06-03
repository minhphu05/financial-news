import { useEffect, useRef, useState } from "react";
import { Bot, ChevronDown, Eraser, Sparkles } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { fetchModels } from "@/api/chat";
import { Button } from "@/components/ui/Button";
import { useChat } from "@/hooks/useChat";

import { ChatInput } from "./ChatInput";
import { ChatMessage } from "./ChatMessage";

interface ChatWindowProps {
  ticker?: string;
  suggestions?: string[];
}

const DEFAULT_SUGGESTIONS = [
  "Tóm tắt tin tức tài chính nổi bật tuần qua.",
  "Lãi suất tiền gửi của các ngân hàng có gì mới?",
  "VN-Index có diễn biến đáng chú ý nào gần đây?",
  "FPT đang công bố thông tin gì?",
];

/** Shorten a full OpenRouter model path to a display label. */
function modelLabel(id: string): string {
  // "deepseek/deepseek-v4-flash:free" → "deepseek-v4-flash"
  const bare = id.split(":")[0];
  return bare.includes("/") ? bare.split("/")[1] : bare;
}

export function ChatWindow({ ticker, suggestions = DEFAULT_SUGGESTIONS }: ChatWindowProps) {
  const { messages, isLoading, send, reset } = useChat();
  const bottomRef = useRef<HTMLDivElement | null>(null);

  // Fetch available models once on mount.
  const { data: modelsData } = useQuery({
    queryKey: ["models"],
    queryFn: fetchModels,
    staleTime: Infinity,
  });
  const [selectedModel, setSelectedModel] = useState<string | undefined>();

  // Once models arrive, default to the server's default.
  useEffect(() => {
    if (modelsData && !selectedModel) {
      setSelectedModel(modelsData.default);
    }
  }, [modelsData, selectedModel]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = (question: string) => {
    void send(question, {
      model: selectedModel,
      ...(ticker ? { filters: { ticker_symbol: ticker } } : {}),
    });
  };

  const showSuggestions = messages.length === 0;

  return (
    <div className="glass flex h-[calc(100vh-9rem)] flex-col rounded-2xl">
      <header className="flex items-center justify-between gap-3 border-b border-ink-800 light:border-ink-200 px-5 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-500/15 text-brand-300">
            <Bot size={18} />
          </div>
          <div className="leading-tight">
            <h2 className="text-sm font-semibold text-ink-50 light:text-ink-900">
              Financial News Assistant
              {ticker && (
                <span className="ml-2 font-mono text-brand-300">· {ticker}</span>
              )}
            </h2>
            <p className="text-xs text-ink-400 light:text-ink-600">
              Trả lời dựa trên kho tin tức tài chính đã thu thập.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Model selector */}
          {modelsData && (
            <div className="relative">
              <select
                value={selectedModel ?? modelsData.default}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="appearance-none rounded-lg border border-ink-700 bg-ink-900 py-1.5 pl-3 pr-8 text-xs text-ink-200 focus:outline-none focus:ring-1 focus:ring-brand-500 light:border-ink-300 light:bg-white light:text-ink-800"
                aria-label="Chọn model"
              >
                {modelsData.models.map((m) => (
                  <option key={m} value={m}>
                    {modelLabel(m)}
                  </option>
                ))}
              </select>
              <ChevronDown
                size={12}
                className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-ink-400"
              />
            </div>
          )}

          <Button
            variant="ghost"
            size="sm"
            onClick={reset}
            disabled={messages.length === 0}
            leftIcon={<Eraser size={14} />}
          >
            Xoá hội thoại
          </Button>
        </div>
      </header>

      <div className="flex-1 space-y-4 overflow-y-auto scroll-thin px-5 py-5">
        {showSuggestions && (
          <div className="flex flex-col gap-4 animate-fade-in">
            <div className="flex items-center gap-2 text-ink-300">
              <Sparkles size={16} className="text-brand-400" />
              <span className="text-sm font-medium">Gợi ý câu hỏi</span>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {suggestions.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => handleSend(s)}
                  className="rounded-xl border border-ink-800 bg-ink-900/50 px-4 py-3 text-left text-sm text-ink-100 transition hover:border-brand-500/40 hover:bg-ink-900 light:border-ink-200 light:bg-white light:text-ink-800 light:hover:border-brand-500/40 light:hover:bg-ink-50"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) => (
          <ChatMessage key={m.id} message={m} />
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-ink-800 light:border-ink-200 p-4">
        <ChatInput onSend={handleSend} disabled={isLoading} />
        <p className="mt-2 text-[11px] text-ink-500">
          Câu trả lời được trích từ kho tin tức CafeF — luôn kiểm tra lại nguồn
          trước khi đưa ra quyết định đầu tư.
        </p>
      </div>
    </div>
  );
}

