#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# Function to wait for Postgres
wait_for_postgres() {
  if [ "$DB_ENGINE" = "django.db.backends.postgresql" ]; then
    echo "Waiting for postgres..."

    while ! nc -z $DB_HOST $DB_PORT; do
      sleep 0.1
    done

    echo "PostgreSQL started"
  fi
}

wait_for_postgres

# Apply database migrations
echo "Applying database migrations..."
python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Execute the main command
exec "$@"
