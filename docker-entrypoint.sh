#!/bin/bash
set -e

# Run database migrations
flask db upgrade

# Start all services via honcho
exec honcho start -f Procfile.dev
