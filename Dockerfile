FROM ubuntu:26.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    curl \
    default-jre-headless \
    git \
    libegl1 \
    libgl1 \
    libgl1-mesa-dri \
    xserver-xorg-core \
    xserver-xorg-video-dummy \
    novnc \
    openbox \
    python3 \
    python3-pip \
    scrot \
    websockify \
    x11-utils \
    x11-xserver-utils \
    x11vnc \
    xdotool \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

COPY xorg.conf /etc/X11/xorg.conf

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Install rustup via apt, then update to latest stable toolchain
RUN apt-get update && apt-get install -y rustup && \
    rustup default stable && \
    rustup update stable
ENV PATH="/root/.cargo/bin:$PATH"

WORKDIR /app

COPY references ./references

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev

COPY *.py ./
COPY docker-entrypoint.sh ./

# Use the Xvfb virtual display and force Mesa software rendering
# (no physical GPU is available inside the container).
ENV DISPLAY=:1
ENV LIBGL_ALWAYS_SOFTWARE=1
ENV PYTHONUNBUFFERED=1

# 5900 = VNC, 6080 = noVNC web interface, 8000 = Build API
EXPOSE 5900 6080 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
