#!/usr/bin/with-contenv bashio
set -euo pipefail

WEBUI_PORT=8788
TERMINAL_PORT=7681
INGRESS_PORT=8787
AGENT_SRC=/opt/hermes-agent-seed
AGENT_DST=/data/hermes/agent-code
WEBUI_SRC=/opt/hermes-webui
WEBUI_DST=/data/hermes/webui-app

TZNAME=$(bashio::config 'timezone')
ENABLE_TERMINAL=$(bashio::config 'enable_terminal')
BROWSER_ENABLED=$(bashio::config 'browser_enabled')
# Existing installations do not yet have this newly added option in options.json.
# Default it on so the already-installed persistent Beeper client survives the update.
BEEPER_ENABLED=$(jq -r '.beeper_enabled // true' /data/options.json)
ASSISTANT_TOOLS_ENABLED=$(bashio::config 'assistant_tools_enabled')
AUTO_UPDATE_AGENT=$(bashio::config 'auto_update_agent')
AUTO_UPDATE_WEBUI=$(bashio::config 'auto_update_webui')
AUTO_CONFIGURE_MCP=$(bashio::config 'auto_configure_mcp')
API_SERVER_ENABLED=$(bashio::config 'api_server_enabled')
API_SERVER_KEY=$(bashio::config 'api_server_key')
DESKTOP_BACKEND_ENABLED=$(bashio::config 'desktop_backend_enabled')
DESKTOP_USERNAME=$(bashio::config 'desktop_username')
DESKTOP_PASSWORD=$(bashio::config 'desktop_password')
USER_HA_TOKEN=$(bashio::config 'homeassistant_token')

if bashio::var.true "${API_SERVER_ENABLED}"; then
    if [ "${#API_SERVER_KEY}" -lt 16 ]; then
        bashio::log.error 'API Server is enabled but its key is missing or shorter than 16 characters. Set a strong api_server_key in the add-on options.'
        bashio::log.error 'A random key can be generated with: openssl rand -hex 32'
        exit 1
    fi
fi

if bashio::var.true "${DESKTOP_BACKEND_ENABLED}"; then
    if [ -z "${DESKTOP_USERNAME}" ] || [ "${#DESKTOP_PASSWORD}" -lt 16 ]; then
        bashio::log.error 'Hermes Desktop requires a username and a password of at least 16 characters in the add-on options.'
        exit 1
    fi
fi

if [ -n "${USER_HA_TOKEN}" ]; then
    HA_TOKEN=${USER_HA_TOKEN}
    HASS_URL=http://homeassistant.local:8123
    bashio::log.info 'Using the configured Home Assistant long-lived token'
elif [ -n "${SUPERVISOR_TOKEN:-}" ]; then
    HA_TOKEN=${SUPERVISOR_TOKEN}
    HASS_URL=http://supervisor/core
    bashio::log.info 'Using the Supervisor token for Home Assistant access'
else
    HA_TOKEN=
    HASS_URL=
    bashio::log.warning 'No Home Assistant token found; Home Assistant tools will be unavailable'
fi

export TZ="${TZNAME}"
if [ -f "/usr/share/zoneinfo/${TZNAME}" ]; then
    cp "/usr/share/zoneinfo/${TZNAME}" /etc/localtime
    printf '%s\n' "${TZNAME}" > /etc/timezone
fi

mkdir -p /data/hermes /data/hermes/webui
export HERMES_HOME=/data/hermes
export HERMES_INSTALL_DIR="${AGENT_DST}"
export UV_NO_CONFIG=1

if bashio::var.true "${ASSISTANT_TOOLS_ENABLED}"; then
    mkdir -p /data/hermes/skills/local-life-assistant /data/hermes/generated
    cp /opt/hermes-addon-skills/local-life-assistant/SKILL.md /data/hermes/skills/local-life-assistant/SKILL.md
    chmod 755 /data/hermes/generated
    chmod 600 /data/hermes/skills/local-life-assistant/SKILL.md
fi

if [ ! -d "${AGENT_DST}/.git" ]; then
    bashio::log.info 'Installing the pinned official Hermes Agent into persistent storage'
    cp -a /opt/hermes-agent-seed "${AGENT_DST}"
fi
if [ ! -x "${AGENT_DST}/.hermes/bin/hermes" ]; then
    bash "${AGENT_DST}/scripts/install.sh" --skip-setup --skip-browser \
        --commit "${HERMES_AGENT_REF}" --branch main --dir "${AGENT_DST}"
fi

AGENT_DIR=${AGENT_DST}
AGENT_CLI="${AGENT_DIR}/.hermes/bin/hermes"
if bashio::var.true "${BROWSER_ENABLED}"; then
    # The same executable/profile is used by native browser tools and Bot Screen.
    export AGENT_BROWSER_EXECUTABLE_PATH=/usr/local/bin/hermes-shared-chromium
fi

ENV_FILE=/data/hermes/.env
(umask 077 && touch "${ENV_FILE}")
for key in HASS_TOKEN HASS_URL API_SERVER_ENABLED API_SERVER_KEY API_SERVER_PORT API_SERVER_HOST; do sed -i "/^${key}=/d" "${ENV_FILE}"; done
if [ -n "${HA_TOKEN}" ]; then
    printf 'HASS_TOKEN=%s\nHASS_URL=%s\n' "${HA_TOKEN}" "${HASS_URL}" >> "${ENV_FILE}"
fi
if bashio::var.true "${API_SERVER_ENABLED}"; then
    printf 'API_SERVER_ENABLED=true\nAPI_SERVER_KEY=%s\nAPI_SERVER_PORT=8642\nAPI_SERVER_HOST=0.0.0.0\n' "${API_SERVER_KEY}" >> "${ENV_FILE}"
fi
chmod 600 "${ENV_FILE}"

HERMES_CONFIG=/data/hermes/config.yaml
if [ ! -f "${HERMES_CONFIG}" ]; then
    if [ -f "${AGENT_DIR}/cli-config.yaml.example" ]; then
        cp "${AGENT_DIR}/cli-config.yaml.example" "${HERMES_CONFIG}"
    else
        printf 'platforms:\n  homeassistant:\n    enabled: true\n' > "${HERMES_CONFIG}"
    fi
fi

# bashio::config emits an empty string for [] and separate values for populated
# arrays. Read the original options JSON so Python always receives one array.
WATCH_ENTITIES=$(jq -c '.watch_entities // []' /data/options.json)
python3 - "${HERMES_CONFIG}" "${HASS_URL}" "${HA_TOKEN}" "${WATCH_ENTITIES}" "${AUTO_CONFIGURE_MCP}" "${ASSISTANT_TOOLS_ENABLED}" <<'PY'
import json
import sys
import yaml

path, hass_url, token, entities_json, configure_mcp, assistant_tools = sys.argv[1:]
entities = json.loads(entities_json)
try:
    with open(path, encoding="utf-8") as stream:
        config = yaml.safe_load(stream) or {}
except FileNotFoundError:
    config = {}
platforms = config.get("platforms") or {}
config["platforms"] = platforms
ha_platform = platforms.setdefault("homeassistant", {})
ha_platform["enabled"] = True
ha_platform.setdefault("extra", {})["watch_entities"] = entities
if configure_mcp == "true" and token:
    servers = config.get("mcp_servers") or {}
    config["mcp_servers"] = servers
    servers["homeassistant"] = {
        "url": f"{hass_url.rstrip('/')}/api/mcp",
        "headers": {"Authorization": f"Bearer {token}"},
    }
if assistant_tools == "true":
    servers = config.get("mcp_servers") or {}
    config["mcp_servers"] = servers
    servers["local_assistant"] = {
        "command": "/usr/bin/python3",
        "args": ["/assistant_tools.py"],
        "timeout": 30,
        "connect_timeout": 15,
    }
else:
    servers = config.get("mcp_servers") or {}
    existing = servers.get("local_assistant")
    if existing and existing.get("command") == "/usr/bin/python3" and existing.get("args") == ["/assistant_tools.py"]:
        del servers["local_assistant"]
with open(path, "w", encoding="utf-8") as stream:
    yaml.safe_dump(config, stream, default_flow_style=False, sort_keys=False)
PY
chmod 600 "${HERMES_CONFIG}"
python3 /browser_setup.py "${HERMES_CONFIG}" /data/options.json

WEBUI_DIR=${WEBUI_DST}
if [ ! -d "${WEBUI_DIR}/.git" ]; then
    bashio::log.info 'Copying the Hermes Web UI checkout into persistent storage'
    cp -a "${WEBUI_SRC}" "${WEBUI_DIR}"
fi

if bashio::var.true "${AUTO_UPDATE_AGENT}" && [ -d "${AGENT_DIR}/.git" ]; then
    bashio::log.info 'Updating Hermes Agent with hermes update'
    "${AGENT_CLI}" update || bashio::log.warning 'Hermes update failed; starting the installed version'
fi
if bashio::var.true "${BROWSER_ENABLED}"; then
    bashio::log.info 'Preparing Hermes native browser tooling (agent-browser)'
    "${AGENT_CLI}" pm install agent-browser || bashio::log.warning 'Native browser tooling could not be installed; see startup output. Chat startup continues.'
fi
if bashio::var.true "${AUTO_UPDATE_WEBUI}" && [ -d "${WEBUI_DIR}/.git" ]; then
    (
        git -C "${WEBUI_DIR}" fetch --depth=1 origin master &&
        git -C "${WEBUI_DIR}" checkout --detach FETCH_HEAD
    ) || bashio::log.warning 'Web UI update failed; starting the installed version'
fi

mkdir -p /data/hermes/logs
if bashio::var.true "${API_SERVER_ENABLED}"; then
    bashio::log.info 'Starting the Hermes gateway daemon and API server on 0.0.0.0:8642'
    # The WebUI health probe needs an explicit URL and the same bearer key.
    # Browser chat keeps its existing in-process backend.
    export HERMES_API_URL=http://127.0.0.1:8642
    export HERMES_WEBUI_GATEWAY_API_KEY="${API_SERVER_KEY}"
else
    bashio::log.info 'Starting the Hermes gateway daemon for scheduled jobs (API server disabled)'
fi
(
    set +e
    while true; do
        # Home Assistant also uses s6. Without --no-supervise Hermes assumes
        # its own Docker image and creates a service that requires /opt/data
        # and a hermes OS user, neither of which exists in this add-on.
        "${AGENT_CLI}" gateway run --no-supervise --external-supervisor \
            >> /data/hermes/logs/gateway.log 2>&1 &
        gateway_pid=$!
        wait "${gateway_pid}"
        rc=$?
        bashio::log.warning "Hermes gateway exited with ${rc}; restarting in 5 seconds"
        sleep 5
    done
) &

AGENT_PYTHON=$(python3 - "${AGENT_DIR}" <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from pm.environments import selected_venv, venv_python

print(venv_python(selected_venv(Path(sys.argv[1]))))
PY
)
WEBUI_REQUIREMENTS_HASH=$(sha256sum "${WEBUI_DIR}/requirements.txt" | awk '{print $1}')
WEBUI_DEPS_MARKER=/data/hermes/.webui-dependencies
WEBUI_DEPS_SIGNATURE="${AGENT_PYTHON}:${WEBUI_REQUIREMENTS_HASH}"
if ! grep -Fxq "${WEBUI_DEPS_SIGNATURE}" "${WEBUI_DEPS_MARKER}" 2>/dev/null; then
    bashio::log.info 'Installing Hermes Web UI dependencies into the Hermes runtime'
    export UV_CACHE_DIR=/data/hermes/.cache/uv
    uv pip install --python "${AGENT_PYTHON}" -r "${WEBUI_DIR}/requirements.txt"
    printf '%s\n' "${WEBUI_DEPS_SIGNATURE}" > "${WEBUI_DEPS_MARKER}"
fi

export HERMES_INSTALL_DIR="${AGENT_DIR}"
export HERMES_WEBUI_AGENT_DIR="${AGENT_DIR}"
export HERMES_WEBUI_STATE_DIR=/data/hermes/webui
export HERMES_WEBUI_HOST=0.0.0.0
export HERMES_WEBUI_PORT=${WEBUI_PORT}
export HERMES_WEBUI_PYTHON="${AGENT_PYTHON}"
export HERMES_CONFIG_PATH="${HERMES_CONFIG}"
export HERMES_WEBUI_PRESERVE_ENV=1

if bashio::var.true "${DESKTOP_BACKEND_ENABLED}"; then
    # Keep the signing key across add-on restarts so Desktop sessions survive.
    # Credentials are passed only to this subprocess and never printed.
    DESKTOP_SECRET_FILE=/data/hermes/.desktop-signing-secret
    if [ ! -s "${DESKTOP_SECRET_FILE}" ]; then
        (umask 077; python3 -c 'import secrets; print(secrets.token_hex(32))' > "${DESKTOP_SECRET_FILE}.tmp"; mv "${DESKTOP_SECRET_FILE}.tmp" "${DESKTOP_SECRET_FILE}")
    fi
    chmod 600 "${DESKTOP_SECRET_FILE}"
    bashio::log.info 'Starting authenticated Hermes Desktop backend on port 9119'
    (
        set +e
        while true; do
            HERMES_DASHBOARD_BASIC_AUTH_USERNAME="${DESKTOP_USERNAME}" \
            HERMES_DASHBOARD_BASIC_AUTH_PASSWORD="${DESKTOP_PASSWORD}" \
            HERMES_DASHBOARD_BASIC_AUTH_SECRET="$(cat "${DESKTOP_SECRET_FILE}")" \
                "${AGENT_CLI}" serve --host 0.0.0.0 --port 9119 \
                >> /data/hermes/logs/desktop-backend.log 2>&1 &
            desktop_pid=$!
            wait "${desktop_pid}"
            rc=$?
            bashio::log.warning "Hermes Desktop backend exited with ${rc}; restarting in 5 seconds"
            sleep 5
        done
    ) &
fi

if bashio::var.true "${BROWSER_ENABLED}"; then
    bashio::log.info 'Starting native Hermes Bot Screen at the protected Ingress path /browser/'
    (
        set +e
        while true; do
            "${AGENT_PYTHON}" /browser_bridge.py &
            browser_bridge_pid=$!
            wait "${browser_bridge_pid}"
            bashio::log.warning 'Bot Screen web adapter exited; retrying in 5 seconds'
            sleep 5
        done
    ) &
fi

if bashio::var.true "${BEEPER_ENABLED}"; then
    bashio::log.info 'Starting persistent Beeper Linux Desktop at the protected Ingress path /beeper/'
    (
        set +e
        while true; do
            /usr/local/bin/hermes-beeper-desktop
            rc=$?
            bashio::log.warning "Beeper desktop stack exited with ${rc}; restarting in 5 seconds"
            sleep 5
        done
    ) &
fi

bashio::log.info "Starting Hermes Web UI through Home Assistant Ingress on :${INGRESS_PORT}"
(
    set +e
    cd "${WEBUI_DIR}"
    while true; do
        "${HERMES_WEBUI_PYTHON}" "${WEBUI_DIR}/server.py" &
        webui_pid=$!
        wait "${webui_pid}"
        rc=$?
        bashio::log.warning "Web UI exited with ${rc}; restarting in 3 seconds"
        sleep 3
    done
) &

if bashio::var.true "${ENABLE_TERMINAL}"; then
    bashio::log.info "Starting setup terminal on the Ingress path /terminal/"
    /usr/local/bin/ttyd --port "${TERMINAL_PORT}" --interface 127.0.0.1 \
        --base-path /terminal --writable --check-origin \
        bash -l -c "
            export HERMES_HOME=/data/hermes
            export HERMES_INSTALL_DIR='${AGENT_DIR}'
            export PATH='${AGENT_DIR}/.hermes/bin:/usr/local/bin:'\"\$PATH\"
            # Keep the shell and an in-progress OAuth listener alive when
            # Home Assistant or the browser drops the terminal WebSocket.
            tmux new-session -d -s hermes-setup -c /data/hermes /terminal-shell.sh 2>/dev/null || true
            tmux set-option -t hermes-setup status off
            exec tmux attach-session -t hermes-setup
        " &
fi

# Hermes fixes the browser OAuth callback at localhost:1455. Forward a LAN
# callback relay on 1456 to that loopback listener while a login is running.
socat TCP-LISTEN:1456,bind=0.0.0.0,reuseaddr,fork TCP:127.0.0.1:1455 &

exec /usr/sbin/nginx -c /etc/nginx/nginx.conf
