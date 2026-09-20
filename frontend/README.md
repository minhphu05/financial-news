# ViFinNER Frontend

React 18 + TypeScript + Vite single-page app for the ViFinNER project.

## Quick start

```bash
cp .env.example .env
npm install
npm run dev
```

App: <http://localhost:5173>

## Scripts

| Command            | Description                              |
|--------------------|------------------------------------------|
| `npm run dev`      | Vite dev server with API proxy.          |
| `npm run build`    | Type-check + production build into `dist/`. |
| `npm run preview`  | Serve the production bundle on :4173.    |
| `npm run lint`     | ESLint over `src/`.                      |
| `npm run typecheck`| `tsc --noEmit`.                          |

## What's inside

* `src/api/`        — axios client + `/stocks`, `/news`, `/chat` endpoints.
* `src/hooks/`      — TanStack Query hooks (`useStocks`, `useNews`, `useChat`).
* `src/components/` — `ui/`, `layout/`, `news/`, `stocks/`, `chat/`.
* `src/pages/`      — Home, News, StockNews, Chat.
* `src/lib/utils.ts` — `cn`, `formatDate`, `formatRelative`, `truncate`.

For the current feature status and the thesis requirements, see
[Project Status](../docs/PROJECT_STATUS.md) and
[Thesis Alignment](../docs/THESIS_ALIGNMENT.md). The current UI links to
the original CafeF article for full text; an in-app article detail page
and stock-price dashboard are not yet implemented.
