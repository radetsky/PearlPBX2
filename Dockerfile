FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput --clear || true

EXPOSE 8000

# Run with uvicorn for ASGI/WebSocket support
CMD ["uvicorn", "pbx.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
