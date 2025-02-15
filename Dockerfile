FROM python:3.12-slim AS build-env

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
    libsodium-dev

COPY --from=ghcr.io/astral-sh/uv:0.5.2 /uv /uvx /bin/

WORKDIR /app

COPY . /app
COPY ./requirements.txt /app

RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install -r requirements.txt && \
    uv pip install git+https://github.com/Rapptz/discord.py --system

COPY ./utils/discord-ext-voice-recv /app/utils/discord-ext-voice-recv
COPY ./install_voice_recv.sh /app
RUN bash ./install_voice_recv.sh
FROM python:3.12-slim AS runtime

COPY --from=build-env /usr/local/bin /usr/local/bin
COPY --from=build-env /usr/local/lib /usr/local/lib
COPY --from=build-env /bin/uv /bin/uv
COPY --from=build-env /bin/uvx /bin/uvx
COPY --from=build-env /app /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TORCH_HOME=/app/torch

WORKDIR /app

RUN mkdir -p ${TORCH_HOME}/hub

RUN adduser -u 1000 --disabled-password --gecos "" appuser

RUN mkdir -p /home/appuser/nltk_data /app/config
RUN chown -R 1000:1000 /app /home/appuser/nltk_data /app/config
USER appuser

CMD ["bash", "-c", "clear; ./entrypoint.sh"]