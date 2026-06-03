import { useCallback, useState } from "react";

import { askChatbot } from "@/api/chat";
import { extractErrorMessage } from "@/api/client";
import type { ChatMessage, ChatRequest } from "@/types";

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const send = useCallback(
    async (question: string, opts?: Omit<ChatRequest, "question">) => {
      const trimmed = question.trim();
      if (!trimmed) return;

      const userTurn: ChatMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content: trimmed,
        createdAt: Date.now(),
      };
      const assistantTurnId = crypto.randomUUID();
      const assistantTurn: ChatMessage = {
        id: assistantTurnId,
        role: "assistant",
        content: "",
        createdAt: Date.now(),
        pending: true,
      };

      setMessages((prev) => [...prev, userTurn, assistantTurn]);
      setIsLoading(true);

      try {
        const response = await askChatbot({ question: trimmed, ...opts });
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantTurnId
              ? {
                  ...m,
                  content: response.answer,
                  citations: response.citations,
                  model: response.model,
                  pending: false,
                }
              : m,
          ),
        );
      } catch (error) {
        const message = extractErrorMessage(error);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantTurnId
              ? { ...m, content: "", error: message, pending: false }
              : m,
          ),
        );
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  const reset = useCallback(() => setMessages([]), []);

  return { messages, isLoading, send, reset };
}

