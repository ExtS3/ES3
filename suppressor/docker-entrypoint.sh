#!/bin/sh
set -e

# Start a virtual X server so headed Chromium (used by the dynamic-analysis
# harness to load MV3 extensions) has a display. Xvfb runs without -auth, so
# clients connect with DISPLAY alone (no XAUTHORITY handshake). The browser is
# launched much later, during a scan, by which point Xvfb is ready.
Xvfb :99 -screen 0 1280x1024x24 -nolisten tcp >/dev/null 2>&1 &
export DISPLAY=:99

# exec so uvicorn becomes PID 1 and receives signals directly.
exec uvicorn main:app --host 0.0.0.0 --port 8001
