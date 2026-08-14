FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on

# Install system dependencies if required by audio processing libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set up work directory
WORKDIR /app

# Upgrade pip and install the uv package manager
RUN pip install --upgrade pip uv

# Copy project specification files
COPY pyproject.toml .
COPY uv.lock .

# Copy the rest of the application payload
COPY src/ ./src/
# gcp-credentials.json is not baked into the image — it is mounted at
# /app/gcp-credentials.json via a Kubernetes secret at deploy time.

# Install dependencies using uv (from pyproject)
RUN uv pip install --system .

# Provide an entrypoint to run the LiveKit agent
ENTRYPOINT ["python", "src/agent.py", "start"]
