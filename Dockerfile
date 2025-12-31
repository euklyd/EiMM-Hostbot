FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for voice support, PostgreSQL client (for pg_dump)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libopus0 \
    libffi-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first for better caching
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy application code
COPY . .

# Make entrypoint executable
RUN chmod +x scripts/entrypoint.sh

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash botuser && \
    chown -R botuser:botuser /app

USER botuser

# Default backup directory (mount a volume here)
ENV BACKUP_DIR=/backups

ENTRYPOINT ["scripts/entrypoint.sh"]
