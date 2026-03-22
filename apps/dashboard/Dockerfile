FROM node:25-alpine AS deps

WORKDIR /app

COPY package*.json ./
RUN npm ci

FROM node:25-alpine AS builder

WORKDIR /app

# Vite inlines VITE_* env vars at build time — declare as ARG so
# Railway service variables are available during `npm run build`.
# NOTE: API_TOKEN is intentionally NOT a VITE_ var — it is injected
# server-side by server.mjs to keep it out of the client JS bundle.
ARG VITE_API_BASE_URL
ARG VITE_WATCHLAB_URL
ARG VITE_PROD_API_BASE_URLS
ARG VITE_ANALYST_VIEW_ENABLED
ARG VITE_DEFAULT_REPORT_VIEW
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY

ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_WATCHLAB_URL=$VITE_WATCHLAB_URL
ENV VITE_PROD_API_BASE_URLS=$VITE_PROD_API_BASE_URLS
ENV VITE_ANALYST_VIEW_ENABLED=$VITE_ANALYST_VIEW_ENABLED
ENV VITE_DEFAULT_REPORT_VIEW=$VITE_DEFAULT_REPORT_VIEW
ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL
ENV VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY

COPY --from=deps /app/node_modules ./node_modules
COPY . .

RUN npm run build

FROM node:25-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

COPY --from=builder /app/server.mjs ./
COPY --from=builder /app/dist ./dist

RUN addgroup --system --gid 1001 appuser && adduser --system --uid 1001 appuser
USER appuser

EXPOSE 4173

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -q --spider http://localhost:${PORT:-4173} || exit 1

CMD ["node", "server.mjs"]
