FROM python:3.12-slim-trixie

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Keep embedding model cache inside the cloud container filesystem (no local host storage)
ENV FASTEMBED_CACHE_PATH=/app/.cache/fastembed \
    HF_HOME=/app/.cache/huggingface \
    HF_HUB_DISABLE_SYMLINKS_WARNING=1 \
    PORT=9417

RUN mkdir -p /app/.cache/fastembed /app/.cache/huggingface

EXPOSE 9417

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-9417}"]
