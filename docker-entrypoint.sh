#!/usr/bin/env bash
set -euo pipefail

# Start a virtual X display at a resolution large enough to house the 854x480
# Minecraft window with room for a window manager title bar.
Xvfb :1 -screen 0 1920x1080x24 -ac &
XVFB_PID=$!

export DISPLAY=:1

# Wait until the X server accepts connections.
for i in $(seq 1 30); do
    if xdpyinfo -display :1 >/dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

# Start a minimal window manager so that windows actually get positioned and
# painted. Openbox is extremely lightweight and sufficient for headless use.
openbox &
sleep 1

# Expose the virtual display over VNC (no password) and wrap it with the
# noVNC web interface so you can watch without a dedicated VNC client:
#   http://localhost:6080/vnc.html
x11vnc -display :1 -nopw -listen 0.0.0.0 -xkb -forever -rfbport 5900 >/dev/null 2>&1 &
websockify --web /usr/share/novnc/ 6080 localhost:5900 >/dev/null 2>&1 &

echo "Started VNC server on http://localhost:6080/vnc.html"
echo "Starting tests in 2s"
sleep 1
echo "Starting tests in 1s"
sleep 1
echo "Running tests now."

# Run the integration tests, forwarding any extra arguments.
exec uv run python main.py "$@"
