# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — Builder
#   Installs gcc/g++ for pyswisseph compilation, then installs all deps into
#   a prefix that gets copied to the final stage.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

# Build tools only needed at compile time
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ make \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .

# Install into an isolated prefix so Stage 2 doesn't need build tools
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — Runtime
#   Minimal image — only what the app needs to run.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# libgomp is needed by pyswisseph at runtime; everything else is already
# statically linked inside the wheel.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy compiled packages from builder
COPY --from=builder /install /usr/local

# ── App files ──────────────────────────────────────────────────────────────
WORKDIR /app

# Copy source (excluding files matched by .dockerignore)
COPY . .

# Ensure the rules file is accessible at the expected relative path
# (config.py uses RULES_FILE = "rules/BPHS_Level2_200_Rules.json")
# Nothing to do — the COPY above handles it.

# ── Runtime config ─────────────────────────────────────────────────────────
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Safe defaults — all overridden by Azure App Service Application Settings
    REDIS_URL=redis://localhost:6379 \
    MONGODB_ENABLED=False

# Azure App Service sets WEBSITES_PORT to tell its proxy which port to forward.
# We always bind on 8000; App Service reads WEBSITES_PORT=8000 from its config.
EXPOSE 8000

# Single worker — APScheduler (midnight IST cron) runs inside this process.
# Keep workers=1 so the batch fires exactly once per day.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
