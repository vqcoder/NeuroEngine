FROM node:20-alpine AS deps

WORKDIR /app

COPY package*.json ./
RUN npm ci

FROM node:20-alpine AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

RUN npm run build

FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

# Required for webpage URL resolution fallback (Vimeo/YouTube/etc).
# Pin yt-dlp to a known-good version range to limit CVE exposure.
# Update periodically: https://github.com/yt-dlp/yt-dlp/releases
RUN apk add --no-cache ffmpeg python3 py3-pip \
  && pip3 install --no-cache-dir --break-system-packages "yt-dlp>=2025.1.15,<2027.0.0"

COPY --from=builder /app/package*.json ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.ts ./next.config.ts

RUN addgroup --system --gid 1001 appuser && adduser --system --uid 1001 appuser
USER appuser

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -q --spider http://localhost:${PORT:-3000}/api/health || exit 1

CMD ["sh", "-c", "npm run start -- -H 0.0.0.0 -p ${PORT:-3000}"]
