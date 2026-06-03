import { ArrowUpRight } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { formatDate } from "@/lib/utils";
import type { Citation } from "@/types";

/**
 * Render a single citation as a compact, clickable card. The score is
 * displayed as a percentage to give users a quick recall signal.
 */
export function CitationCard({ citation }: { citation: Citation }) {
  const scorePct = Math.round(citation.score * 100);
  return (
    <a
      href={citation.article_link}
      target="_blank"
      rel="noreferrer"
      className="group block rounded-lg border border-ink-800 bg-ink-900/50 p-3 transition-colors hover:border-brand-500/40 hover:bg-ink-900"
    >
      <div className="flex items-center gap-2">
        <Badge tone="brand" className="font-mono">
          [{citation.index}]
        </Badge>
        {citation.ticker_symbol && (
          <Badge tone="muted" className="font-mono">
            {citation.ticker_symbol}
          </Badge>
        )}
        <span className="ml-auto text-xs font-mono text-ink-400">{scorePct}%</span>
      </div>
      <p className="mt-2 line-clamp-2 text-sm font-medium text-ink-100 group-hover:text-brand-200">
        {citation.title || citation.article_link}
      </p>
      <div className="mt-1 flex items-center justify-between text-xs text-ink-500">
        <span>{citation.post_date || formatDate(undefined)}</span>
        <ArrowUpRight size={12} className="opacity-60 group-hover:opacity-100" />
      </div>
    </a>
  );
}
