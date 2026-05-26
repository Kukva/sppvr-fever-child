# Multi-stage build for backend
FROM python:3.11-slim-bookworm as base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Switch to Yandex mirror for fast downloads from Russia
RUN echo 'deb http://mirror.yandex.ru/debian/ bookworm main contrib non-free non-free-firmware\ndeb-src http://mirror.yandex.ru/debian/ bookworm main contrib non-free non-free-firmware\n\ndeb http://security.debian.org/debian-security bookworm-security main contrib non-free non-free-firmware\ndeb-src http://security.debian.org/debian-security bookworm-security main contrib non-free non-free-firmware\n\ndeb http://mirror.yandex.ru/debian/ bookworm-updates main contrib non-free non-free-firmware\ndeb-src http://mirror.yandex.ru/debian/ bookworm-updates main contrib non-free non-free-firmware' > /etc/apt/sources.list

# Install system dependencies and fonts for PDF (Cyrillic)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    postgresql-client \
    curl \
    netcat-openbsd \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set work directory
WORKDIR /app

# Development stage
FROM base as development

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/exports/pdf /app/logs

# Change ownership
RUN chown -R appuser:appuser /app

# Switch to app user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run development server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Production stage
FROM base as production

# Install only production dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Ensure writable dirs exist and are owned by appuser (fix PermissionError in container)
RUN mkdir -p /app/exports/pdf /app/logs && chown -R appuser:appuser /app

# Install additional production dependencies
RUN pip install gunicorn

# Create startup script
RUN echo '#!/bin/bash\n\
set -e\n\
echo "Starting Fever Routing Backend..."\n\
\n\
# Wait for database\n\
echo "Waiting for database..."\n\
while ! nc -z postgres 5432; do\n\
  sleep 0.1\n\
done\n\
echo "Database is ready"\n\
\n\
# Run migrations (if needed)\n\
# alembic upgrade head\n\
\n\
# Start application\n\
echo "Starting application..."\n\
exec gunicorn app.main:app \\\n\
  --bind 0.0.0.0:8000 \\\n\
  --workers 4 \\\n\
  --worker-class uvicorn.workers.UvicornWorker \\\n\
  --worker-connections 1000 \\\n\
  --max-requests 1000 \\\n\
  --max-requests-jitter 100 \\\n\
  --timeout 300 \\\n\
  --keep-alive 2 \\\n\
  --access-logfile - \\\n\
  --error-logfile - \\\n\
  --capture-output \\\n\
  --log-level info\n\
' > /app/start.sh && chmod +x /app/start.sh

# Switch to app user (ownership already set above)
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start application
CMD ["/app/start.sh"]

# Testing stage
FROM development as testing

# Install test dependencies
RUN pip install pytest pytest-asyncio pytest-cov httpx

# Run tests
CMD ["pytest", "tests/", "-v", "--cov=app", "--cov-report=html", "--cov-report=term"]