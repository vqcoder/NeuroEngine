# Pin to exact patch to prevent silent breakage from Docker Hub tag updates.
# When upgrading, regenerate readout_guardian_baseline.json and run deploy-gate.
FROM python:3.14.3-slim

WORKDIR /service

# Node.js 20+ is required by yt-dlp's EJS challenge solver for YouTube.
# Debian Bookworm ships Node 18 which is too old.
RUN apt-get update \
  && apt-get install -y --no-install-recommends ffmpeg curl ca-certificates gnupg \
  && mkdir -p /etc/apt/keyrings \
  && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
     | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
  && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
     > /etc/apt/sources.list.d/nodesource.list \
  && apt-get update \
  && apt-get install -y --no-install-recommends nodejs \
  && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic

RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -e .

RUN groupadd --gid 1001 appuser && useradd --uid 1001 --gid appuser --create-home appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -sf http://localhost:${PORT:-8000}/health || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
