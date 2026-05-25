FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    curl \
    default-jre-headless \
    libegl1 \
    libgl1 \
    libgl1-mesa-dri \
    novnc \
    openbox \
    python3 \
    python3-pip \
    scrot \
    websockify \
    x11-utils \
    x11vnc \
    xdotool \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev

COPY *.py ./
COPY docker-entrypoint.sh ./

# Use the Xvfb virtual display and force Mesa software rendering
# (no physical GPU is available inside the container).
ENV DISPLAY=:1
ENV LIBGL_ALWAYS_SOFTWARE=1
ENV PYTHONUNBUFFERED=1

# 5900 = VNC, 6080 = noVNC web interface
EXPOSE 5900 6080

ENTRYPOINT ["/app/docker-entrypoint.sh"]
