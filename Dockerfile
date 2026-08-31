# Use python:3.12-slim as the base image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    pkg-config \
    libcairo2-dev \
    libjpeg-dev \
    zlib1g-dev \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js (needed for SASS build)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install global sass via npm
RUN npm install -g sass

# Install uv for fast Python package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set work directory
WORKDIR /app

# Copy npm dependency files and install first to leverage cache
COPY package.json package-lock.json ./
RUN npm ci

# Copy the rest of the application code (necessary for Python package metadata and version resolution)
COPY . .

# Install python dependencies via uv (system-wide, including development packages)
RUN uv pip install --system . --group dev --group docker

# Compile CSS from SASS
RUN npm run build:css:sass

# Expose port 8000
EXPOSE 8000

# Set default settings module
ENV DJANGO_SETTINGS_MODULE=settings.main

# Make entrypoint script executable
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Entrypoint script will run migrations on startup without touching user data
ENTRYPOINT ["/app/docker-entrypoint.sh"]

