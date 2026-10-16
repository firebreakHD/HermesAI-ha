# Changelog

## 2.0.7

- Adds local keyless MCP tools for weather forecasts, addresses, distances and driving routes. The home origin is read automatically from Home Assistant `zone.home`.
- Creates responsive HTML previews that Hermes Desktop can display inside chat, with weather charts and one-click Google Maps, Apple Maps and OpenStreetMap links.
- Teaches the Home Assistant WebUI to replace `::preview` directives with the protected inline card, including the mobile layout.
- Extends the existing Preferences quota toggle with a slim composer indicator for both free 5-hour and weekly provider quota.
- Installs a managed life-assistant skill plus `LIFE_ASSISTANT_PROMPT.txt` for predictable preview rendering and quiet late-night wellbeing reminders while an active Desktop session can see current activity.

## 2.0.6

- Adds an optional authenticated `hermes serve` backend on port 9119 for the official Hermes Desktop app. Credentials are configured in the Home Assistant add-on options; the host port is assigned separately under Network.
- Keeps the Desktop signing secret in persistent add-on storage so Desktop sessions survive restarts. The existing OpenAI-compatible API on port 8642 remains separate.

## 2.0.5

- Integriert den vorhandenen Hermes Bot Screen mit persistentem, sichtbarem Chromium und lokaler manueller Übernahme. Keine zusätzliche Agenten- oder MCP-Browserimplementierung.
- Fügt Bildschirm-Pakete und noVNC ausschließlich im Add-on-Image hinzu. Der Webadapter verwendet Hermes' native Laufzeit, Dateisperre und RFB-Eingabefilter; der Zugriff erfolgt nur über HA-Ingress.
- Browser und Setup-Terminal liegen oben im einklappbaren Menü „Werkzeuge“ und verdecken mobil nicht mehr den Senden-Button.
- Hält die Kontrolle nach Verbindungsverlust gesperrt; nach Rückgabe wird im Chat mit „Weiter“ fortgesetzt.
- Ergänzt Konfigurationswiederherstellung, Adaptertests, Build-Prüfungen und einen kopierbaren gemeinsamen Abnahmetest.

## 2.0.4 — 2026-10-14

- Preserve interactive terminal commands across browser or Ingress WebSocket
  disconnects so Codex browser authorization can finish and the result can be
  seen after reconnecting.

## 2.0.3 — 2026-10-14

- Prevent the gateway from registering Hermes' own Docker s6 service inside
  the Home Assistant base image; use the add-on's foreground supervisor.

## 2.0.2 — 2026-10-14

- Keep the gateway daemon running for scheduled tasks even when the API server
  is disabled.
- Give the WebUI its local gateway URL and API key for an accurate status pill.

## 2.0.1 — 2026-10-14

- Fixed the startup crash while reading an empty or populated
  `watch_entities` option.
- Updated repository metadata to the published `HermesAI-ha` address.

## 2.0.0 — 2026-10-14

- Updated the agent backend to the official NousResearch Hermes source.
- Preserved the established Hermes WebUI and the integrated setup terminal.
- Added Codex browser OAuth support and an optional localhost callback relay.
- Added persistent terminal-driven Hermes updates.
- Enabled the official authenticated Hermes API server on port 8642 for JARVIS.
- Kept Home Assistant token, MCP, watched-entity, timezone, and update options.
- Added localized option labels and Home Assistant image metadata.
