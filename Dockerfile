# ── Stage 1: build the web dashboard frontend (React → static files) ─────────
FROM node:22-slim AS dashboard-build
WORKDIR /build
RUN corepack enable
COPY web_dashboard/frontend/package.json web_dashboard/frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY web_dashboard/frontend/ ./
RUN pnpm build

# ── Stage 2: Python runtime ───────────────────────────────────────────────────
FROM python:3.14-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire project
COPY . .

# Built dashboard frontend, served by web_dashboard/server.py
COPY --from=dashboard-build /build/dist /app/web_dashboard/frontend/dist

# Generate build manifest from files actually baked into this image.
# This guarantees the container verifier always compares against the
# correct hashes and never triggers false-positive DeploymentDrift alerts.
RUN python scripts/generate_build_manifest.py

# Create data directories if they don't exist
RUN mkdir -p /app/data/logs /app/data/live /app/data/historical

# Set environment for unbuffered output (real-time logs)
ENV PYTHONUNBUFFERED=1

# Runtime guard: signals to main.py that we are inside the container.
# main.py checks this and exits immediately if the value is absent,
# preventing accidental execution via systemd or bare `python main.py`.
ENV RUNNING_IN_DOCKER=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8501/healthz', timeout=5)" || exit 1

# Default: run scheduler in paper trading mode
CMD ["python", "main.py", "--schedule", "--paper"]
