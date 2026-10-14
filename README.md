# Hermes Agent für Home Assistant

[![Build and publish Home Assistant add-on](https://github.com/firebreakHD/HermesAI-ha/actions/workflows/build.yml/badge.svg)](https://github.com/firebreakHD/HermesAI-ha/actions/workflows/build.yml)

Eine Home Assistant Portierung des offiziellen
[Hermes Agent von NousResearch](https://github.com/NousResearch/hermes-agent):
mit der bekannten
[Hermes WebUI](https://github.com/nesquena/hermes-webui), integriertem Terminal
und dauerhaft laufendem Gateway. Das Add-on bringt Hermes in die Home Assistant
Sidebar und stellt bei Bedarf seine API für andere Anwendungen bereit.

Der Agent wird aus dem offiziellen NousResearch Repository geladen. Dieses
Community-Add-on wird unabhängig von NousResearch gepflegt und enthält die
Verpackung, Konfiguration und Startlogik für Home Assistant.

## Funktionen

- Hermes WebUI und Setup Terminal direkt über Home Assistant Ingress
- Offizieller Hermes Agent mit persistenten Daten unter `/data/hermes`
- Gateway Daemon für geplante Jobs und den optionalen API Server
- OpenAI-kompatible Hermes API für JARVIS und andere Clients auf Port `8642`
- Home Assistant Zugriff über den Supervisor Token; optionales MCP und
  überwachte Entities
- Browser Login für Codex Konten mit
  `hermes auth add openai-codex --browser`
- Updates für Agent, WebUI und Add-on über ihre jeweiligen Wege
- Container Images für `amd64` und `aarch64`

## Installation

1. In Home Assistant **Einstellungen → Add-ons/Apps → Add-on-Store → ⋮ → Repositories** öffnen.
2. Dieses Repository hinzufügen:

   ```text
   https://github.com/firebreakHD/HermesAI-ha
   ```

3. **Hermes Assistant** installieren.
4. In den Add-on Optionen einen zufälligen, mindestens 16 Zeichen langen
   `api_server_key` eintragen, sofern `api_server_enabled` aktiv bleibt. Die
   übrigen Optionen nach Bedarf einstellen und das Add-on starten.
5. **Hermes Agent** in der Sidebar öffnen. Im Terminal `hermes setup` ausführen
   und einen Modellanbieter einrichten.

Der erste Start installiert die Hermes Laufzeit im persistenten Add-on-Speicher
und kann einige Minuten dauern. Zugangsdaten und Sitzungen bleiben bei einem
Add-on Neustart erhalten.

Die vollständigen Optionen und die Einrichtung von Codex Browser Login,
Home Assistant MCP und externen API Clients stehen in der
[Add-on Dokumentation](hermes_assistant/DOCS.md).

## API und Netzwerk

| Dienst | Adresse | Hinweis |
| --- | --- | --- |
| WebUI und Terminal | Home Assistant Sidebar | Läuft über Ingress; keine eigene Portfreigabe nötig. |
| Hermes API | `http://<REPO-ID>-hermes-assistant:8642` | Interne Adresse für andere Home Assistant Add-ons, ohne `/v1` als Basisadresse. |
| Hermes API vom Heimnetz | `http://<HOME-ASSISTANT-IP>:8642` | Benötigt den `api_server_key`; der Host Port ist in den Netzwerk Einstellungen änderbar. |
| Codex Browser Rückruf | Host Port `1456` | Optional und standardmäßig deaktiviert; nur während des Logins benötigt. |

Der Gateway Daemon läuft auch dann für geplante Aufgaben, wenn
`api_server_enabled` ausgeschaltet ist. Sein Zustand lässt sich im Add-on
Terminal mit `hermes gateway status` prüfen.

## Updates

| Komponente | Aktualisierung |
| --- | --- |
| Home Assistant Add-on | Über Home Assistant, nachdem der [GitHub Actions Build](https://github.com/firebreakHD/HermesAI-ha/actions/workflows/build.yml) für die neue Version erfolgreich abgeschlossen ist. |
| Hermes Agent | `hermes update` im Add-on Terminal oder `auto_update_agent` beim Start. |
| Hermes WebUI | `auto_update_webui` aktualisiert den separaten WebUI-Quellcode beim Start. |

Eine neue Versionsnummer im Repository kann schon sichtbar sein, während das
zugehörige Container Image noch gebaut wird. In diesem Zeitraum kann ein
Home Assistant Update mit einem Pull Fehler scheitern. Nach dem erfolgreichen
Build das Add-on Repository in Home Assistant neu laden und das Update erneut
starten. Die genaue Ursache steht im **Supervisor Protokoll**; die allgemeine
WebSocket Meldung von `update.install` allein reicht zur Diagnose nicht aus.

## Projekt und Herkunft

- [`hermes_assistant/`](hermes_assistant/): Add-on Konfiguration, Image und Dokumentation
- [`CHANGELOG.md`](CHANGELOG.md): Änderungen pro Add-on Version
- [`RELEASING.md`](RELEASING.md): Veröffentlichung und Images für Maintainer
- [`THIRD_PARTY.md`](THIRD_PARTY.md): Upstream Projekte und Lizenzen
- [`codex-browser-callback-proxy.ps1`](codex-browser-callback-proxy.ps1): optionale Windows Hilfe für den Codex Browser Rückruf

Hermes Agent und WebUI werden beim Image Build aus ihren jeweiligen
Original-Repositories geladen. Ihre initialen Versionen sind im
[`Dockerfile`](hermes_assistant/Dockerfile) festgelegt.
