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

See [`docs/en/12_frontend.md`](../docs/en/12_frontend.md) (or
[`docs/vi/12_giao_dien.md`](../docs/vi/12_giao_dien.md)) for the long
form.
