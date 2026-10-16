ARG BUILD_FROM=ghcr.io/home-assistant/base-debian:bookworm

FROM ${BUILD_FROM} AS builder

ARG HERMES_AGENT_REF=0e427d788d253630d38a3a51cd76849e73cd6925
ARG HERMES_WEBUI_REF=v0.52.76
ARG TTYD_VERSION=1.7.7

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_CONFIG=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git python3 python3-venv build-essential python3-dev \
      libffi-dev libssl-dev ripgrep && \
    rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in amd64) ttyd_arch=x86_64 ;; arm64) ttyd_arch=aarch64 ;; *) exit 1 ;; esac; \
    curl -fsSL "https://github.com/tsl0922/ttyd/releases/download/${TTYD_VERSION}/ttyd.${ttyd_arch}" -o /opt/ttyd; \
    curl -fsSL "https://raw.githubusercontent.com/tsl0922/ttyd/${TTYD_VERSION}/LICENSE" -o /opt/ttyd-LICENSE; \
    chmod +x /opt/ttyd; /opt/ttyd --version

RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin INSTALLER_NO_MODIFY_PATH=1 sh

# Keep the official checkout pinned in the image. Its installer runs at first
# boot against /data so Hermes' PM runtime and updatable code share the same
# persistent HERMES_HOME and install paths.
RUN git clone --filter=blob:none --no-checkout --depth=1 \
      https://github.com/NousResearch/hermes-agent.git /opt/hermes-agent-seed && \
    git -C /opt/hermes-agent-seed fetch --depth=1 origin "${HERMES_AGENT_REF}" && \
    git -C /opt/hermes-agent-seed checkout --detach FETCH_HEAD

# Keep the exact Hermes web UI used by the existing add-on, pinned to a
# current upstream tag. Its Python runtime uses Hermes' managed environment.
RUN git clone --depth=1 --branch "${HERMES_WEBUI_REF}" https://github.com/nesquena/hermes-webui.git /opt/hermes-webui && \
    git -C /opt/hermes-webui rev-parse HEAD

FROM ${BUILD_FROM} AS runtime

ARG BUILD_VERSION=2.0.8
ARG BUILD_ARCH=amd64

LABEL io.hass.version="${BUILD_VERSION}" \
      io.hass.type="app" \
      io.hass.arch="${BUILD_ARCH}" \
      io.hass.name="Hermes Assistant" \
      io.hass.description="Official Hermes Agent with Web UI and terminal for Home Assistant" \
      io.hass.url="https://github.com/firebreakHD/HermesAI-ha" \
      org.opencontainers.image.title="Hermes Assistant" \
      org.opencontainers.image.description="Official Hermes Agent with Web UI and terminal for Home Assistant" \
      org.opencontainers.image.source="https://github.com/firebreakHD/HermesAI-ha" \
      org.opencontainers.image.version="${BUILD_VERSION}"

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HERMES_HOME=/data/hermes \
    HERMES_AGENT_REF=0e427d788d253630d38a3a51cd76849e73cd6925 \
    HERMES_WEBUI_AGENT_DIR=/data/hermes/agent-code \
    HERMES_WEBUI_STATE_DIR=/data/hermes/webui \
    HERMES_WEBUI_HOST=0.0.0.0 \
    HERMES_WEBUI_PORT=8787 \
    PATH=/usr/local/bin:/usr/bin:/bin

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git bash jq python3 python3-yaml build-essential \
      python3-dev libffi-dev libssl-dev openssh-client ffmpeg ripgrep nginx-light socat tmux && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Hermes' native Bot Screen and its shared headed browser (no second agent).
RUN apt-get update && apt-get install -y --no-install-recommends \
      tigervnc-standalone-server xfce4-panel xfwm4 xfdesktop4 xfce4-settings \
      xfce4-terminal dbus-x11 x11-xserver-utils x11-utils xauth fonts-dejavu-core \
      chromium novnc && apt-get clean && rm -rf /var/lib/apt/lists/*
RUN cp -Lr /usr/share/novnc /browser_novnc

COPY --from=builder /opt/ttyd /usr/local/bin/ttyd
COPY --from=builder /opt/ttyd-LICENSE /usr/share/doc/ttyd/LICENSE
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv
COPY --from=builder /usr/local/bin/uvx /usr/local/bin/uvx
COPY --from=builder /opt/hermes-agent-seed /opt/hermes-agent-seed
COPY --from=builder /opt/hermes-webui /opt/hermes-webui

RUN printf '%s\n' \
    '#!/bin/bash' \
    'if [ -x /data/hermes/agent-code/.hermes/bin/hermes ]; then exec /data/hermes/agent-code/.hermes/bin/hermes "$@"; fi' \
    'echo "Hermes is not installed; see add-on startup log" >&2; exit 127' \
    > /usr/local/bin/hermes && chmod +x /usr/local/bin/hermes && \
    mkdir -p /run/nginx /var/log/nginx

COPY run.sh /run.sh
COPY browser_bridge.py /browser_bridge.py
COPY browser_setup.py /browser_setup.py
COPY assistant_tools.py /assistant_tools.py
COPY assistant_ui.js /assistant_ui.js
COPY LIFE_ASSISTANT_PROMPT.txt /LIFE_ASSISTANT_PROMPT.txt
COPY life_assistant_skill /opt/hermes-addon-skills/local-life-assistant
COPY shared-chromium.sh /usr/local/bin/hermes-shared-chromium
COPY browser_view /browser_view
COPY terminal-shell.sh /terminal-shell.sh
COPY nginx.conf /etc/nginx/nginx.conf
RUN chmod +x /run.sh /terminal-shell.sh /usr/local/bin/hermes-shared-chromium

EXPOSE 8787 7681 8642 1456 9119
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8787/health || exit 1

CMD ["/run.sh"]
