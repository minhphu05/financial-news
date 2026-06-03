import { Outlet } from "react-router-dom";

import { Header } from "./Header";
import { Sidebar } from "./Sidebar";

/**
 * Application shell. Renders the header at the top, a sticky sidebar with
 * the VN50 list on the left, and the active route inside the main area.
 */
export function Layout() {
  return (
    <div className="min-h-screen text-ink-100 light:text-ink-800">
      <Header />
      <div className="mx-auto max-w-7xl px-4 sm:px-6 pb-12 pt-6">
        <div className="grid gap-6 lg:grid-cols-[18rem_minmax(0,1fr)]">
          <div className="hidden lg:block">
            <Sidebar />
          </div>
          <main className="min-h-[calc(100vh-9rem)]">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
