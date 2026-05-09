# ──────────────────────────────────────────────
# Stage 1: dependency builder
# ──────────────────────────────────────────────
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ──────────────────────────────────────────────
# Stage 2: runtime image
# ──────────────────────────────────────────────
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/install/bin:$PATH" \
    PYTHONPATH="/install/lib/python3.13/site-packages"

WORKDIR /app

# Runtime system deps only (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /install

# Create a non-root user for security
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

# Copy application code
COPY . .

# Give ownership to the app user
RUN mkdir -p /app/staticfiles /app/media \
    && chown -R appuser:appgroup /app

USER appuser

# Copy and register entrypoint
COPY --chown=appuser:appgroup docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]

# Production: gunicorn | Development: override with runserver
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
