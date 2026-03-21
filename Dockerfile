# syntax=docker/dockerfile:1
# =============================================================================
# Stage 1 — builder: compiles C extensions, installs all Python deps
# Only this stage needs build-essential and git.
# =============================================================================
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libsodium-dev \
    swig \
    libpulse-dev \
    libasound2-dev && \
    rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install Python deps — cached layer, only rebuilds when requirements.txt changes
COPY requirements.txt ./
RUN uv pip install --system -r requirements.txt

# Install local voice extension — cached separately from main deps
COPY ./utils/discord-ext-voice-recv ./utils/discord-ext-voice-recv
RUN uv pip install --system -U ./utils/discord-ext-voice-recv


# =============================================================================
# Stage 2 — runtime: lean image, no build tools
# =============================================================================
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TORCH_HOME=/app/torch \
    NLTK_DATA=/home/appuser/nltk_data

# Runtime system deps only — no build-essential, vim, git, or ping
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    ffmpeg \
    libffi8 \
    libsodium23 \
    curl && \
    rm -rf /var/lib/apt/lists/*

# Copy compiled packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Create user and directories in a single layer
RUN adduser -u 1000 --disabled-password --gecos "" appuser && \
    mkdir -p /app/torch/hub /home/appuser/nltk_data /app/config /app/data /app/logs && \
    chown -R 1000:1000 /app /home/appuser/nltk_data

WORKDIR /app

# Copy application source — COPY --chown avoids a separate chown layer
COPY --chown=1000:1000 . /app

USER appuser

CMD ["bash", "-c", "clear; ./entrypoint.sh"]
