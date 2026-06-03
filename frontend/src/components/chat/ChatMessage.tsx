import { AlertTriangle, Bot, User } from "lucide-react";
import ReactMarkdown from "react-markdown";

import { Spinner } from "@/components/ui/Spinner";
import { cn } from "@/lib/utils";
import type { ChatMessage as ChatMessageType } from "@/types";

import { CitationCard } from "./CitationCard";

/**
 * Render a single conversation turn.
 *
 * The assistant bubble supports three visual states:
 *
 * 1. ``pending`` — show a spinner while the LLM is generating.
 * 2. ``error`` — show a red bubble with the error message.
 * 3. Normal — render markdown + citation grid.
 */
export function ChatMessage({ message }: { message: ChatMessageType }) {
  const isUser = message.role === "user";
  return (
    <div
      className={cn(
        "flex gap-3 animate-slide-up",
        isUser ? "flex-row-reverse" : "flex-row",
      )}
    >
      <div
        className={cn(
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-full",
          isUser ? "bg-ink-800 text-ink-200" : "bg-brand-500/15 text-brand-300",
        )}
      >
        {isUser ? <User size={16} /> : <Bot size={16} />}
      </div>

      <div
        className={cn(
          "flex max-w-[88%] flex-col gap-2 rounded-xl px-4 py-3 text-sm leading-relaxed",
          isUser
            ? "bg-brand-500/15 text-ink-50 ring-brand"
            : "glass text-ink-100",
        )}
      >
        {message.pending ? (
          <Spinner label="Đang suy nghĩ..." />
        ) : message.error ? (
          <p className="inline-flex items-center gap-2 text-rose-300">
            <AlertTriangle size={14} />
            {message.error}
          </p>
        ) : (
          <div className="prose prose-invert prose-sm max-w-none">
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </div>
        )}

        {message.citations && message.citations.length > 0 && (
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            {message.citations.map((c) => (
              <CitationCard key={`${message.id}-${c.index}`} citation={c} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
