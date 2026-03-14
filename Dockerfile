FROM python:3.12-slim

# Group common environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TORCH_HOME=/app/torch \
    NLTK_DATA=/home/appuser/nltk_data \
    UV_CACHE_DIR=/root/.cache/uv

# Install system dependencies (slowest, rarely changes)
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -yy --no-install-recommends --no-install-suggests \
    build-essential \
    ca-certificates \
    python3-setuptools \
    vim \
    ffmpeg \
    libffi-dev \
    git \
    curl \
    iputils-ping \
    libsodium-dev && \
    rm -rf /var/lib/apt/lists/*

# Add uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:0.5.2 /uv /uvx /bin/

WORKDIR /app

# Pre-install main Python dependencies (changes when requirements.txt changes)
# Corrected cache mount target to /root/.cache/uv
COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r requirements.txt && \
    uv pip install --system git+https://github.com/Rapptz/discord.py

# Pre-install local extension (changes when the extension code changes)
COPY ./utils/discord-ext-voice-recv /app/utils/discord-ext-voice-recv
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -U /app/utils/discord-ext-voice-recv

# Setup environment and directories (does not change with code)
RUN adduser -u 1000 --disabled-password --gecos "" appuser && \
    mkdir -p ${TORCH_HOME}/hub ${NLTK_DATA} /app/config && \
    chown -R 1000:1000 /app /home/appuser/nltk_data

# Copy the rest of the application (changes frequently)
COPY . /app

# Final permission fix for the rest of the copied files
RUN chown -R 1000:1000 /app

USER appuser

# Standardize entrypoint
CMD ["bash", "-c", "clear; ./entrypoint.sh"]
