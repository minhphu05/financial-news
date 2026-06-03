import { useRef, useState, type KeyboardEvent } from "react";
import { Send } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";

interface ChatInputProps {
  onSend: (value: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

/**
 * Auto-growing textarea + send button. Pressing Enter sends; Shift+Enter
 * inserts a newline.
 */
export function ChatInput({ onSend, disabled, placeholder }: ChatInputProps) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  const send = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
    if (ref.current) ref.current.style.height = "auto";
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      send();
    }
  };

  return (
    <div
      className={cn(
        "glass rounded-2xl p-2.5 flex items-end gap-2",
        "focus-within:border-brand-500/40 focus-within:ring-1 focus-within:ring-brand-500/30",
      )}
    >
      <textarea
        ref={ref}
        rows={1}
        value={value}
        placeholder={placeholder ?? "Đặt câu hỏi về tin tức tài chính... (Enter để gửi)"}
        onChange={(e) => {
          setValue(e.target.value);
          // auto-grow
          e.currentTarget.style.height = "auto";
          e.currentTarget.style.height = `${Math.min(e.currentTarget.scrollHeight, 160)}px`;
        }}
        onKeyDown={onKeyDown}
        disabled={disabled}
        className={cn(
          "flex-1 resize-none bg-transparent text-sm text-ink-100 placeholder:text-ink-500",
          "outline-none px-3 py-2 leading-relaxed max-h-40 scroll-thin",
        )}
      />
      <Button
        type="button"
        size="md"
        onClick={send}
        disabled={disabled || !value.trim()}
        leftIcon={<Send size={15} />}
      >
        Gửi
      </Button>
    </div>
  );
}
