#!/bin/bash
set -e

echo "Waiting for database to be ready..."
until pg_isready -h "${PGHOST}" -U "${PGUSER}"; do
  echo "Database not ready, retrying in 5s..."
  sleep 5
done

echo "Creating database if it does not exist..."
psql -h "${PGHOST}" -U "${PGUSER}" -tc \
  "SELECT 1 FROM pg_database WHERE datname = 'notification_api'" \
  | grep -q 1 || psql -h "${PGHOST}" -U "${PGUSER}" -c "CREATE DATABASE notification_api"

echo "Running database migrations..."
flask db upgrade

echo "Starting services..."
exec honcho start -f Procfile.dev
