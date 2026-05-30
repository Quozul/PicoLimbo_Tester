#!/usr/bin/env bash
set -euo pipefail

# Start a real Xorg server using the dummy video driver.
# This provides a real XRandR display mode list, fixing LWJGL 2 crashes.
Xorg :1 -config /etc/X11/xorg.conf -noreset -logfile /dev/stdout &
X_PID=$!

export DISPLAY=:1
export PATH="/root/.cargo/bin:$PATH"

# Disable X access control so that tools like x11vnc and xdotool can connect.
# We wait a bit for Xorg to initialize first.
sleep 2
xhost + >/dev/null 2>&1 || true

# Wait until the X server accepts connections.
MAX_RETRIES=30
COUNT=0
while ! xdpyinfo -display :1 >/dev/null 2>&1; do
    if [ $COUNT -ge $MAX_RETRIES ]; then
        echo "❌ Xorg failed to start or become available after $MAX_RETRIES seconds."
        kill $X_PID 2>/dev/null || true
        exit 1
    fi
    echo "Waiting for Xorg to start..."
    sleep 1
    COUNT=$((COUNT + 1))
done

echo "✅ Xorg is running."

# Start a minimal window manager so that windows actually get positioned and
# painted. Openbox is extremely lightweight and sufficient for headless use.
openbox &
OPENBOX_PID=$!
sleep 1

# Expose the virtual display over VNC (no password) and wrap it with the
# noVNC web interface so you can watch without a dedicated VNC client:
#   http://localhost:6080/vnc.html
x11vnc -display :1 -nopw -listen 0.0.0.0 -xkb -forever -rfbport 5900 >/dev/null 2>&1 &
X11VNC_PID=$!
websockify --web /usr/share/novnc/ 6080 localhost:5900 >/dev/null 2>&1 &
WEBSOCKIFY_PID=$!

echo "Started VNC server on http://localhost:6080/vnc.html"

# Start the PicoLimbo Build API
echo "Starting PicoLimbo Build API on port 8000..."
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info &
API_PID=$!

echo "PicoLimbo Build API is running on http://localhost:8000"
echo "API documentation available at http://localhost:8000/docs"

# Trap SIGINT and SIGTERM to kill all child processes
cleanup() {
    echo "Shutting down..."
    kill $X_PID $OPENBOX_PID $X11VNC_PID $WEBSOCKIFY_PID $API_PID 2>/dev/null || true
    wait 2>/dev/null || true
    echo "All processes stopped."
}
trap cleanup SIGINT SIGTERM

# Wait for all background processes
wait

