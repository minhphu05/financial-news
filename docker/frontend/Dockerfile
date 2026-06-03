# =============================================================================
# Multi-stage build for the ViFinNER React frontend.
# Stage 1 — install + build with Node.
# Stage 2 — serve the static bundle with nginx.
# =============================================================================

FROM node:20-alpine AS builder
WORKDIR /app

# Better cache: copy manifests first.
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund

COPY frontend/ ./

# Bake the API base URL at build time. Override via:
#   docker compose build --build-arg VITE_API_BASE_URL=https://api.example.com
ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

# -----------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

COPY docker/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

# Healthcheck hits the SPA index — useful for compose & orchestrators.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -q -O- http://127.0.0.1/ > /dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
