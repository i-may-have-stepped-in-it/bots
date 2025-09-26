FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TORCH_HOME=/app/torch

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

COPY --from=ghcr.io/astral-sh/uv:0.5.2 /uv /uvx /bin/

WORKDIR /app

COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    uv pip install --system --no-cache-dir -r requirements.txt
RUN uv pip install --system git+https://github.com/Rapptz/discord.py

COPY ./utils/discord-ext-voice-recv /app/utils/discord-ext-voice-recv
COPY ./install_voice_recv.sh /app
COPY . /app

RUN bash ./install_voice_recv.sh &&\
    rm -rf /root/.cache/pip

RUN mkdir -p ${TORCH_HOME}/hub

RUN adduser -u 1000 --disabled-password --gecos "" appuser
RUN mkdir -p /home/appuser/nltk_data /app/config
RUN chown -R 1000:1000 /app /home/appuser/nltk_data /app/config

USER appuser

CMD ["bash", "-c", "clear; ./entrypoint.sh"]