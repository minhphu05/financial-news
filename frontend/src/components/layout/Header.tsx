import { NavLink } from "react-router-dom";
import { Bot, Github, LineChart, Moon, Newspaper, Sun } from "lucide-react";

import { cn } from "@/lib/utils";
import { useTheme } from "@/hooks/useTheme";

const NAV = [
  { to: "/", label: "Tổng quan", icon: LineChart },
  { to: "/news", label: "Tin tức", icon: Newspaper },
  { to: "/chat", label: "Chatbot", icon: Bot },
] as const;

/**
 * Top navigation bar. Sticky, glassy, brand-coloured logo on the left;
 * route links in the center; theme toggle + action area on the right.
 */
export function Header() {
  const { theme, toggle } = useTheme();

  return (
    <header
      className={cn(
        "sticky top-0 z-30 border-b backdrop-blur",
        "border-ink-800 bg-ink-950/80",
        "light:border-ink-200 light:bg-white/90",
      )}
    >
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-4 sm:px-6">
        <NavLink to="/" className="flex items-center gap-2.5">
          <img src="/logo.svg" alt="Financial News" className="h-8 w-8" />
          <div className="flex flex-col leading-tight">
            <span className="text-base font-semibold text-ink-50 light:text-ink-900">
              Financial News
            </span>
            <span className="text-[11px] uppercase tracking-wider text-brand-400 light:text-brand-600">
              Tin tức tài chính · AI
            </span>
          </div>
        </NavLink>

        <nav className="ml-6 hidden md:flex items-center gap-1">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                cn(
                  "inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-brand-500/10 text-brand-300 light:text-brand-700 light:bg-brand-500/15"
                    : "text-ink-300 hover:bg-ink-800/60 hover:text-ink-100 light:text-ink-600 light:hover:bg-ink-100 light:hover:text-ink-900",
                )
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={toggle}
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-ink-300 hover:bg-ink-800/60 hover:text-ink-100 light:text-ink-600 light:hover:bg-ink-100 light:hover:text-ink-900 transition-colors"
            aria-label="Chuyển giao diện sáng/tối"
            title={theme === "dark" ? "Chế độ sáng" : "Chế độ tối"}
          >
            {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <a
            href="https://github.com/"
            target="_blank"
            rel="noreferrer"
            className="hidden sm:inline-flex h-9 w-9 items-center justify-center rounded-lg text-ink-300 hover:bg-ink-800/60 hover:text-ink-100 light:text-ink-600 light:hover:bg-ink-100 light:hover:text-ink-900 transition-colors"
            aria-label="GitHub"
          >
            <Github size={18} />
          </a>
        </div>
      </div>
    </header>
  );
}
