FROM python:3.11-slim

# Install system dependencies for voice support, PostgreSQL client (for pg_dump)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libopus0 \
    libffi-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user early (before copying files)
RUN useradd --create-home --shell /bin/bash botuser

# Set up app directory with correct ownership
WORKDIR /app
RUN chown botuser:botuser /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first for better caching
COPY --chown=botuser:botuser pyproject.toml uv.lock ./

# Switch to non-root user and install dependencies
USER botuser
RUN uv sync --frozen --no-dev

# Copy application code (--chown avoids slow recursive chown later)
COPY --chown=botuser:botuser . .

# Make entrypoint executable
RUN chmod +x scripts/entrypoint.sh

# Create backup directory with correct ownership
RUN mkdir -p /app/backups
ENV BACKUP_DIR=/app/backups

ENTRYPOINT ["scripts/entrypoint.sh"]
