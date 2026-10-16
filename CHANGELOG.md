# Changelog

## 2.0.7 — 2026-10-16 (staged)

- Add local, keyless Hermes tools for weather, addresses, distances and driving routes using Home Assistant's home location, Open-Meteo and OpenStreetMap/OSRM.
- Generate mobile-friendly weather and route previews for Hermes Desktop, including one-click Google Maps, Apple Maps and OpenStreetMap links.
- Render those generated previews directly inside the Home Assistant Hermes chat instead of showing the raw `::preview` directive.
- Show both free 5-hour and weekly provider quota in a compact composer row controlled by the existing Preferences toggle.
- Install a managed life-assistant skill and a copyable prompt for consistent tool cards, previews and restrained late-night reminders in active Desktop sessions.

## 2.0.6 — 2026-10-16 (staged)

- Add an optional authenticated `hermes serve` endpoint for Hermes Desktop on internal port 9119, with username and password in the Home Assistant add-on configuration and a selectable host port under Network.
- Persist the Desktop session signing secret and restart the backend after unexpected exits. Port 8642 remains the separate OpenAI-compatible API.

## 2.0.5 — 2026-10-15

- Add the native Hermes Bot Screen with a shared persistent Chromium browser, manual takeover, and a Home Assistant Ingress viewer. No separate agent or MCP browser is introduced.
- Move Browser and Setup Terminal into a collapsed top toolbar so they no longer cover the mobile chat composer.
- Add native browser configuration restoration, input-lease adapter tests and image package checks. The real shared-tab takeover test remains required on the HA device.

## 2.0.4 — 2026-10-14

- Keep the setup shell and browser OAuth listener alive when the Home Assistant
  Ingress terminal WebSocket disconnects. Reopening the terminal reattaches to
  the running session instead of killing the login command.

## 2.0.3 — 2026-10-14

- Run the Hermes gateway in foreground mode under the add-on's restart loop.
  This prevents Hermes from creating an incompatible s6 service that expects
  `/opt/data` and a `hermes` system user.

## 2.0.2 — 2026-10-14

- Run the Hermes gateway daemon independently of the optional API server so
  scheduled jobs continue to fire.
- Connect the WebUI gateway health probe to the local API server with the
  configured bearer key when the API server is enabled.

## 2.0.1 — 2026-10-14

- Fixed startup when `watch_entities` is empty or contains multiple entries.
- Updated repository links to the published `firebreakHD/HermesAI-ha` address.

## 2.0.0 — 2026-10-14

- Rebuilt the add-on around the current official NousResearch Hermes Agent.
- Kept the established Hermes WebUI, HA Ingress sidebar entry, and integrated
  terminal layout.
- Added support for the Codex OAuth browser flow
  (`hermes auth add openai-codex --browser`) with an optional local callback
  relay.
- Added persistent Hermes installation and terminal-driven `hermes update`.
- Enabled the official authenticated Hermes API server on port 8642 for JARVIS.
- Retained Home Assistant token, MCP, watched-entity, timezone, and automatic
  update configuration.
- Added multi-architecture GitHub Actions builds and GHCR publishing.
- Added Home Assistant image labels, option translations, release instructions,
  and GitHub repository metadata for `firebreakHD/HermesAI-ha`.
