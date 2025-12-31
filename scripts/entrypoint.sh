#!/bin/bash
set -e

BACKUP_DIR="${BACKUP_DIR:-/backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"

# Extract connection info from DATABASE_URL for pg_dump
# Format: postgresql+asyncpg://user:pass@host:port/dbname
parse_database_url() {
    # Remove the driver prefix (postgresql+asyncpg://)
    local url="${DATABASE_URL#*://}"

    # Extract user:pass
    local userpass="${url%%@*}"
    export PGUSER="${userpass%%:*}"
    export PGPASSWORD="${userpass#*:}"

    # Extract host:port/dbname
    local hostpart="${url#*@}"
    local hostport="${hostpart%%/*}"
    export PGHOST="${hostport%%:*}"
    export PGPORT="${hostport#*:}"

    # Handle case where port isn't specified
    if [ "$PGPORT" = "$PGHOST" ]; then
        export PGPORT="5432"
    fi

    export PGDATABASE="${hostpart#*/}"
}

check_pending_migrations() {
    # Returns 0 if there are pending migrations, 1 if up to date
    local current=$(alembic current 2>/dev/null | grep -oE '[a-f0-9]+' | head -1)
    local head=$(alembic heads 2>/dev/null | grep -oE '[a-f0-9]+' | head -1)

    if [ -z "$head" ]; then
        # No migrations exist yet
        echo "No migrations found"
        return 1
    fi

    if [ "$current" = "$head" ]; then
        echo "Database is up to date (revision: $current)"
        return 1
    else
        echo "Pending migrations: $current -> $head"
        return 0
    fi
}

backup_database() {
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_file="${BACKUP_DIR}/pre_migration_${timestamp}.sql.gz"

    echo "Backing up database to $backup_file..."
    mkdir -p "$BACKUP_DIR"

    parse_database_url

    pg_dump --no-password | gzip > "$backup_file"

    if [ $? -eq 0 ]; then
        echo "Backup completed: $backup_file"

        # Clean up old backups
        echo "Cleaning up backups older than $BACKUP_RETENTION_DAYS days..."
        find "$BACKUP_DIR" -name "pre_migration_*.sql.gz" -mtime +$BACKUP_RETENTION_DAYS -delete
    else
        echo "ERROR: Backup failed!"
        exit 1
    fi
}

run_migrations() {
    echo "Running database migrations..."
    alembic upgrade head

    if [ $? -eq 0 ]; then
        echo "Migrations completed successfully"
    else
        echo "ERROR: Migrations failed!"
        echo "You may need to restore from backup: $BACKUP_DIR"
        exit 1
    fi
}

main() {
    echo "=== EiMM-Hostbot Startup ==="

    if [ -z "$DATABASE_URL" ]; then
        echo "WARNING: DATABASE_URL not set, skipping migrations"
    else
        if check_pending_migrations; then
            backup_database
            run_migrations
        fi
    fi

    echo "Starting bot..."
    exec python bidoof.py "$@"
}

main "$@"
