#!/bin/bash
# Reset the development database and seed with test data.
#
# Usage:
#   ./scripts/reset_dev_db.sh           # Reset and seed
#   ./scripts/reset_dev_db.sh --no-seed # Reset only, no seed data
#
# Prerequisites:
#   - Docker Compose postgres service running
#   - DB_PASSWORD set in .env or environment

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Load .env if it exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Check for required env vars
if [ -z "$DB_PASSWORD" ]; then
    echo "Error: DB_PASSWORD not set. Create a .env file with DB_PASSWORD=yourpassword"
    exit 1
fi

# Check if postgres is running
if ! docker compose ps postgres | grep -q "running"; then
    echo "Starting postgres..."
    docker compose up -d postgres
    echo "Waiting for postgres to be healthy..."
    sleep 5
fi

echo "=== Resetting Database ==="

# Drop and recreate schema (faster than dropping/recreating database)
echo "Dropping schema..."
docker compose exec -T postgres psql -U eimm -d eimm -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"

echo "Running migrations..."
uv run alembic upgrade head

# Seed unless --no-seed flag
if [ "$1" != "--no-seed" ]; then
    echo ""
    echo "=== Seeding Test Data ==="
    DATABASE_URL="postgresql+asyncpg://eimm:${DB_PASSWORD}@localhost:5432/eimm" \
        uv run python scripts/seed_test_data.py
else
    echo ""
    echo "Skipping seed (--no-seed flag provided)"
fi

echo ""
echo "=== Done ==="
echo "Database is ready for testing."
