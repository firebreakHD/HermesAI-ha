#!/bin/bash
set -euo pipefail

BEEPER_HOME=/data/hermes/beeper-cli
BEEPER_APP="${BEEPER_HOME}/apps/desktop/extracted/squashfs-root/AppRun"
BEEPER_PROFILE="${BEEPER_HOME}/profiles/desktop/linux-desktop"
BEEPER_INSTALLATIONS="${BEEPER_HOME}/installations.json"
RUNTIME_DIR=/run/hermes-beeper
DISPLAY=:98
LOG_DIR="${BEEPER_HOME}/logs"

mkdir -p "${BEEPER_PROFILE}" "${LOG_DIR}" "${RUNTIME_DIR}"
chmod 700 "${BEEPER_HOME}" "${BEEPER_PROFILE}" "${LOG_DIR}" "${RUNTIME_DIR}"

export BEEPER_CLI_CONFIG_DIR="${BEEPER_HOME}"
export DISPLAY
export HOME="${BEEPER_HOME}"
export XDG_CONFIG_HOME="${BEEPER_HOME}/config"
export XDG_DATA_HOME="${BEEPER_HOME}/data"
export XDG_CACHE_HOME="${BEEPER_HOME}/cache"
export NO_AT_BRIDGE=1
mkdir -p "${XDG_CONFIG_HOME}" "${XDG_DATA_HOME}" "${XDG_CACHE_HOME}"
chmod 700 "${XDG_CONFIG_HOME}" "${XDG_DATA_HOME}" "${XDG_CACHE_HOME}"

cleanup() {
    set +e
    for pid in "${BEEPER_PID:-}" "${WEBSOCKIFY_PID:-}" "${X11VNC_PID:-}" "${WM_PID:-}" "${XVFB_PID:-}"; do
        [ -n "${pid}" ] && kill "${pid}" 2>/dev/null
    done
    rm -f "${RUNTIME_DIR}"/*.pid
}
trap cleanup EXIT INT TERM

rm -f /tmp/.X98-lock /tmp/.X11-unix/X98
Xvfb :98 -screen 0 1920x1200x24 -nolisten tcp >"${LOG_DIR}/xvfb.log" 2>&1 &
XVFB_PID=$!
printf '%s\n' "${XVFB_PID}" >"${RUNTIME_DIR}/xvfb.pid"

for _ in $(seq 1 100); do
    xdpyinfo -display :98 >/dev/null 2>&1 && break
    kill -0 "${XVFB_PID}" 2>/dev/null || { echo 'Beeper Xvfb exited during startup' >&2; exit 1; }
    sleep 0.1
done
xdpyinfo -display :98 >/dev/null 2>&1 || { echo 'Beeper display :98 did not become ready' >&2; exit 1; }

# Give Beeper normal window decorations and close/minimize controls on its
# dedicated display. The image already contains xfwm4 for the browser desktop.
xfwm4 --compositor=off >"${LOG_DIR}/xfwm4.log" 2>&1 &
WM_PID=$!
printf '%s\n' "${WM_PID}" >"${RUNTIME_DIR}/xfwm4.pid"
sleep 1
kill -0 "${WM_PID}" 2>/dev/null || { echo 'Beeper window manager exited during startup' >&2; exit 1; }

# Both services listen on loopback only. Home Assistant exposes only nginx's
# authenticated Ingress route; no VNC, WebSocket or debug port is published.
x11vnc -display :98 -localhost -rfbport 5901 -forever -shared -nopw -quiet \
    >"${LOG_DIR}/x11vnc.log" 2>&1 &
X11VNC_PID=$!
printf '%s\n' "${X11VNC_PID}" >"${RUNTIME_DIR}/x11vnc.pid"
websockify --web=/browser_novnc 127.0.0.1:9011 127.0.0.1:5901 \
    >"${LOG_DIR}/websockify.log" 2>&1 &
WEBSOCKIFY_PID=$!
printf '%s\n' "${WEBSOCKIFY_PID}" >"${RUNTIME_DIR}/websockify.pid"

while kill -0 "${XVFB_PID}" 2>/dev/null; do
    if ! kill -0 "${WM_PID}" 2>/dev/null || ! kill -0 "${X11VNC_PID}" 2>/dev/null || ! kill -0 "${WEBSOCKIFY_PID}" 2>/dev/null; then
        echo 'Beeper Ingress bridge exited; restarting the complete stack' >&2
        exit 1
    fi
    BEEPER_IMAGE=$(jq -r '.desktop.path // empty' "${BEEPER_INSTALLATIONS}" 2>/dev/null || true)
    if [ -z "${BEEPER_IMAGE}" ] || [ ! -f "${BEEPER_IMAGE}" ]; then
        echo 'Beeper installations.json does not reference an existing verified desktop AppImage; waiting without launching' >&2
        sleep 15
        continue
    fi
    if [ ! -x "${BEEPER_APP}" ]; then
        echo "Verified extracted Beeper AppRun is missing: ${BEEPER_APP}" >&2
        echo 'The add-on will not download or trust an unverified replacement automatically.' >&2
        sleep 15
        continue
    fi

    "${BEEPER_APP}" --no-sandbox --disable-gpu --ozone-platform=x11 \
        --user-data-dir="${BEEPER_PROFILE}" >>"${LOG_DIR}/desktop.log" 2>&1 &
    BEEPER_PID=$!
    printf '%s\n' "${BEEPER_PID}" >"${RUNTIME_DIR}/beeper.pid"
    # Electron restores its old 1200x800 window size after a display resize.
    # Keep the entire Beeper window and its controls inside the dedicated screen.
    for _ in $(seq 1 30); do
        BEEPER_WINDOW=$(xdotool search --onlyvisible --name '^Beeper$' 2>/dev/null | head -n 1 || true)
        if [ -n "${BEEPER_WINDOW}" ]; then
            xdotool windowsize "${BEEPER_WINDOW}" 1840 1120
            xdotool windowmove "${BEEPER_WINDOW}" 40 40
            break
        fi
        sleep 0.5
    done
    set +e
    wait -n "${BEEPER_PID}" "${XVFB_PID}" "${WM_PID}" "${X11VNC_PID}" "${WEBSOCKIFY_PID}"
    rc=$?
    set -e
    if kill -0 "${BEEPER_PID}" 2>/dev/null; then
        echo 'Beeper display or Ingress bridge exited; restarting the complete stack' >&2
        exit 1
    fi
    rm -f "${RUNTIME_DIR}/beeper.pid"
    BEEPER_PID=
    echo "Beeper Desktop exited with ${rc}; restarting in 5 seconds" >&2
    sleep 5
done

wait "${XVFB_PID}"
