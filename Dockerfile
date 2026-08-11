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

RUN chmod +x docker-entrypoint.sh

EXPOSE 8000

# Idempotently migrate + collectstatic on every start, then run the CMD
ENTRYPOINT ["./docker-entrypoint.sh"]

# Run with uvicorn for ASGI/WebSocket support
CMD ["uvicorn", "pbx.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
