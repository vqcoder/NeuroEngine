# Pin to exact patch to prevent silent breakage from Docker Hub tag updates.
# When upgrading, regenerate readout_guardian_baseline.json and run deploy-gate.
FROM python:3.14.3-slim

WORKDIR /service

RUN apt-get update \
  && apt-get install -y --no-install-recommends ffmpeg curl \
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
