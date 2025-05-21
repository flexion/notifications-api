# Multi-stage build for notifications-api
FROM python:3.12-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    git \
    curl \
    make \
    && rm -rf /var/lib/apt/lists/*

# Copy application code
COPY . .

# Install pip and wheel
RUN pip install --upgrade pip wheel setuptools

# Install Poetry using the official installer
ENV POETRY_HOME=/opt/poetry
ENV POETRY_VERSION=1.8.2
RUN curl -sSL https://install.python-poetry.org | python3 - && \
    ln -s /opt/poetry/bin/poetry /usr/local/bin/poetry

# Configure poetry to not create a virtual environment
RUN poetry config virtualenvs.create false

# Set git commit info for version.py - use a more explicit approach
ARG GIT_COMMIT=local
RUN echo "__git_commit__ = \"${GIT_COMMIT}\"" > app/version.py && \
    echo "__time__ = \"$(date +%Y-%m-%d:%H:%M:%S)\"" >> app/version.py

# Install dependencies (no dev dependencies for smaller image)
RUN poetry install --only main --no-interaction

# Final stage
FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies and PostgreSQL client for database creation
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependencies from builder stage
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Copy generated version.py from builder
COPY --from=builder /app/app/version.py /app/app/version.py

# Explicitly install honcho (it's in dev dependencies but we need it for runtime)
RUN pip install honcho==2.0.0

# Set environment variables
ENV FLASK_APP=application.py
ENV REDIS_ENABLED=1
ENV NOTIFY_ENVIRONMENT=development
ENV NOTIFY_APP_NAME=api
ENV API_HOST_NAME=http://localhost:6011
ENV WERKZEUG_DEBUG_PIN=off

# Default test user account for local development
ENV NOTIFY_E2E_TEST_EMAIL=example@fake.gov
ENV NOTIFY_E2E_TEST_PASSWORD=testpassword

# Create database user for PostgreSQL connection
ENV DATABASE_URL=postgresql://postgres:postgres@db:5432/notification_api
ENV SQLALCHEMY_DATABASE_TEST_URI=postgresql://postgres:postgres@db:5432/test_notification_api

# Set Redis URL to connect to Redis container
ENV REDIS_URL=redis://redis:6379

# Expose the port the app runs on
EXPOSE 6011

# Add curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Add a health check
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:6011/_status || exit 1

# Create a script to initialize the database and start the application
RUN echo '#!/bin/bash\n\
echo "Waiting for PostgreSQL to be ready..."\n\
until PGPASSWORD=postgres psql -h db -U postgres -c "SELECT 1" > /dev/null 2>&1; do\n\
  echo "PostgreSQL is unavailable - sleeping 1 second"\n\
  sleep 1\n\
done\n\
\n\
echo "Creating databases if they do not exist..."\n\
PGPASSWORD=postgres psql -h db -U postgres -c "CREATE DATABASE notification_api;" 2>/dev/null || echo "notification_api database already exists"\n\
PGPASSWORD=postgres psql -h db -U postgres -c "CREATE DATABASE test_notification_api;" 2>/dev/null || echo "test_notification_api database already exists"\n\
\n\
echo "Running database migrations..."\n\
flask db upgrade\n\
\n\
echo "Creating test user if it does not exist..."\n\
echo "${NOTIFY_E2E_TEST_EMAIL}\nA Name\n${NOTIFY_E2E_TEST_PASSWORD}\n${NOTIFY_E2E_TEST_PASSWORD}" | flask command create-test-user --admin=True || echo "Test user already exists"\n\
\n\
exec "$@"\n' > /app/docker-entrypoint.sh

RUN chmod +x /app/docker-entrypoint.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Create a custom Procfile.dev.docker with direct commands instead of make targets
RUN echo "web: flask run -p 6011 --host=0.0.0.0" > Procfile.dev.docker && \
    echo "worker: celery -A run_celery.notify_celery worker --loglevel=INFO --concurrency=2 --max-memory-per-child=512000" >> Procfile.dev.docker && \
    echo "scheduler: celery -A run_celery.notify_celery beat --loglevel=INFO" >> Procfile.dev.docker

# Use our custom Procfile instead of the original one
CMD ["honcho", "start", "-f", "Procfile.dev.docker"]