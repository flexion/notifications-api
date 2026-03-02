FROM python:3.13-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    postgresql-client \
    curl \
    git \
    make \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
ENV POETRY_VERSION=1.8.5
RUN curl -sSL https://install.python-poetry.org | python3 - && \
    ln -s /root/.local/bin/poetry /usr/local/bin/poetry

WORKDIR /app

# Copy poetry configuration files
COPY pyproject.toml poetry.lock ./

# Install Python dependencies (no virtualenv in container)
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --no-root

# Copy the rest of the application
COPY . .

# Generate version file
ARG GIT_COMMIT=local
RUN echo "__git_commit__ = \"${GIT_COMMIT}\"" > app/version.py && \
    echo "__time__ = \"$(date +%Y-%m-%d:%H:%M:%S)\"" >> app/version.py

ENV FLASK_APP=application.py
ENV PYTHONPATH=/app

EXPOSE 6011

HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:6011/_status || exit 1

# Run migrations then start all services
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
CMD ["/docker-entrypoint.sh"]
