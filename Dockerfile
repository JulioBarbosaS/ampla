# Ampla server (hub + panel) in one image — GitLab-Omnibus-style:
# the hub serves the API, the WebSocket and the built React panel on one port.

# Stage 1 — build the web panel
FROM node:22-alpine AS web
RUN corepack enable
WORKDIR /web
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
# Same-origin: the panel calls whatever host it is served from (no baked URL).
RUN pnpm build

# Stage 2 — hub runtime, serving the panel built above
FROM python:3.12-slim AS hub
WORKDIR /app
COPY hub/ ./
RUN pip install --no-cache-dir -e .
COPY --from=web /web/dist /app/web-dist
COPY docker-entrypoint.sh /usr/local/bin/amp-entrypoint
RUN chmod +x /usr/local/bin/amp-entrypoint

ENV AMP_ENVIRONMENT=production \
    AMP_WEB_DIST=/app/web-dist \
    AMP_DATABASE_URL=sqlite+aiosqlite:////data/amp.db
EXPOSE 8000
VOLUME /data
ENTRYPOINT ["amp-entrypoint"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
