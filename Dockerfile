# Stage 1: Build frontend
FROM node:20-slim AS frontend

# Base path for the frontend (e.g., "/iv" for yourdomain.com/iv/)
ARG VITE_BASE_PATH=/iv/

WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
ENV VITE_BASE_PATH=${VITE_BASE_PATH}
RUN npm run build

# Stage 2: Python application
FROM python:3.12-slim

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

# Copy built frontend from stage 1
COPY --from=frontend --chown=botuser:botuser /frontend/../web/static ./web/static

# Make entrypoint executable
RUN chmod +x scripts/entrypoint.sh

# Create backup directory with correct ownership
RUN mkdir -p /app/backups
ENV BACKUP_DIR=/app/backups

# Expose web interface port
EXPOSE 8080

ENTRYPOINT ["scripts/entrypoint.sh"]
