# For more information, please refer to https://aka.ms/vscode-docker-python
FROM python:3.12-slim

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1
ENV TORCH_HOME=/app/torch
RUN mkdir -p ${TORCH_HOME}/hub
RUN chmod -R 777 /app/
# Install necessary dependencies
RUN apt-get update -qy
RUN apt-get upgrade -qy
RUN apt-get install -qyy \
    -o APT::Install-Recommends=false \
    -o APT::Install-Suggests=false \
    build-essential \
    ca-certificates \
    python3-setuptools \
    vim \
    ffmpeg \
    libffi-dev \
    git \
    curl \
    iputils-ping\
    libsodium-dev 
# Set the working directory
WORKDIR /app
COPY ./requirements.txt /app
COPY --from=ghcr.io/astral-sh/uv:0.5.2 /uv /uvx /bin/
# RUN pip3 install --upgrade pip
RUN pip3 install -r requirements.txt

# Copy the application files to the container
COPY . /app
RUN bash ./install_voice_recv.sh
# Clone the discord.py repository and install it
RUN uv pip install git+https://github.com/Rapptz/discord.py --system
# RUN pip install invokeai[xformers] --use-pep517 --extra-index-url https://download.pytorch.org/whl/cu121

# Creates a non-root user with an explicit UID and adds permission to access the /app folder
# # For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
RUN adduser -u 1000 --disabled-password --gecos "" appuser && chown -R appuser /app

# Create the /app/config directory and set ownership to appuser
RUN mkdir -p /app/config && chown -R 1000:1000 /app/config
RUN mkdir /home/appuser/nltk_data
RUN chmod -R 777 /home/appuser/nltk_data && chown -R 1000:1000 /home/appuser/nltk_data

# Switch to the appuser
USER appuser

# During debugging, this entry point will be overridden.
# For more information, please refer to https://aka.ms/vscode-docker-python-debug
CMD ["bash", "-c", "clear; ./entrypoint.sh"]
