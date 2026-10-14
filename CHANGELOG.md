# Changelog

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
