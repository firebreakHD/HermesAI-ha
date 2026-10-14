# Hermes Assistant für Home Assistant

Dieses Repository enthält ein eigenständiges Home-Assistant-Add-on. Die WebUI,
der Terminal-Einstieg über die Sidebar, Ingress, Supervisor-Token, MCP-Anbindung
und Add-on-Optionen folgen dem vorhandenen Hermes-Add-on. Das Image enthält den
gepinnten offiziellen Hermes-Agent-Quellstand und die bisherige Hermes-WebUI.
Beim ersten Start installiert Hermes seine Laufzeit persistent. Der
Terminal-Befehl `hermes update`
aktualisiert den persistenten Agent-Code unabhängig vom Add-on-Image.

## Ordner

- `hermes_assistant/`: vollständiges Home-Assistant-Add-on
- `codex-browser-callback-proxy.ps1`: optionale Windows-Weiterleitung für
  Codex-Login per `--browser` aus dem Add-on-Terminal
- `RELEASING.md`: GitHub-Veröffentlichung und Versionsablauf
- `THIRD_PARTY.md`: verwendete Upstream-Projekte und Lizenzen

Das öffentliche Repository ist `firebreakHD/HermesAI-ha`. Hinweise zu GHCR,
Home Assistant und späteren Updates stehen in [RELEASING.md](RELEASING.md).

## Installieren

1. Den erfolgreichen GitHub-Actions-Build im Repository
   `firebreakHD/HermesAI-ha` abwarten. Danach die GHCR-Pakete
   `amd64-hermes-assistant` und `aarch64-hermes-assistant` jeweils auf
   **Public** stellen. Ein öffentliches GitHub-Repository allein macht seine
   Container-Pakete nicht automatisch öffentlich.
2. In Home Assistant: **Einstellungen → Add-ons → Add-on-Store → ⋮ → Repositories**.
3. Die URL des neuen GitHub-Repositories hinzufügen und **Hermes Assistant**
   installieren.
4. Vor dem ersten Start in den Add-on-Optionen einen `api_server_key` setzen;
   bei aktiviertem API Server ist der Schlüssel erforderlich. Zeitzone,
   Home-Assistant-Integration und Update-Optionen ebenfalls einstellen.
5. Add-on starten. Hermes installiert seine Laufzeit beim ersten Start im
   persistenten Add-on-Speicher; dieser Start dauert mehrere Minuten. Danach
   in der Sidebar **Hermes Agent** öffnen.
6. Im WebUI-Terminal `hermes setup` ausführen und den gewünschten Anbieter
   einrichten.

Persistente Hermes-Konfiguration und Anmeldedaten liegen unter
`/data/hermes` im Add-on-Datenverzeichnis. Zugangsdaten für Modellanbieter
werden im Terminal mit `hermes setup` oder `hermes auth` eingerichtet und
bleiben bei Add-on-Neustarts erhalten.

Für JARVIS ist Hermes' OpenAI-kompatibler API Server standardmäßig aktiviert.
Trage in den Add-on-Optionen einen starken `api_server_key` ein und starte das
Add-on neu. Für JARVIS innerhalb von Home Assistant verwende die interne
Add-on-Adresse `http://<REPO-ID>-hermes-assistant:8642` (ohne `/v1`). Die
Repository-ID steht bei den Home-Assistant-Add-ons; bei einer lokalen
Installation lautet sie `local`. Für Zugriffe außerhalb des Add-on-Netzes
verwende `http://<HOME-ASSISTANT-IP>:<HOST-PORT>`; der Standard-Host-Port ist
`8642`. Bei einem Port-Konflikt kannst du den Host-Port in den
Netzwerk-Einstellungen des Add-ons ändern.
Unter Windows kannst du einen zufälligen Schlüssel mit PowerShell erzeugen:

```powershell
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
$bytes = New-Object byte[] 32
$rng.GetBytes($bytes)
[BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
$rng.Dispose()
```

## Codex-Konto mit Browser-Login hinzufügen

Der aktuelle Upstream unterstützt den Befehl:

```sh
hermes auth add openai-codex --browser
```

OpenAI leitet den Browser fest an `http://localhost:1455/auth/callback`
zurück. Hermes wartet im Add-on-Container auf einen HTTP-Aufruf dieser Adresse;
das Einfügen der Rückgabe-URL in die laufende Terminaleingabe reicht nicht.
So geht es ohne zusätzliches Skript:

1. In der Add-on-Netzwerk-Konfiguration den optionalen Port `1456/tcp` auf
   Host-Port `1456` abbilden und das Add-on neu starten. Port `1456` ist
   standardmäßig **nicht** geöffnet.
2. Im Add-on-Terminal `hermes auth add openai-codex --browser` starten und die
   angezeigte Anmelde-URL auf dem Browser-PC öffnen. Das Terminal wartet nun
   auf den Rückruf.
3. Nach dem Login zeigt der Browser möglicherweise einen Verbindungsfehler bei
   `http://localhost:1455/auth/callback?code=...&state=...`. In der Adresszeile
   **nur** `localhost:1455` durch `<HOME-ASSISTANT-IP>:1456` ersetzen; Pfad und
   gesamte Abfrage unverändert lassen. Die geänderte URL öffnen. Das Add-on
   leitet den Rückruf intern an Hermes weiter.
4. Nach erfolgreichem Login die Port-Abbildung `1456/tcp` wieder entfernen.

Alternativ kann der Rückruf automatisch weitergeleitet werden. Dafür nach
Schritt 1 **vor** dem Öffnen der Anmelde-URL das beiliegende Skript auf dem
Browser-PC starten:

```powershell
.\codex-browser-callback-proxy.ps1 -HomeAssistantHost 192.168.1.20
```

`192.168.1.20` durch die IP-Adresse von Home Assistant ersetzen. Nach dem
Login das Skript beenden und die Port-Abbildung entfernen.

Die Rückgabe-URL enthält einen einmaligen Anmeldecode: nicht in Chats oder Logs
teilen. Das Skript speichert weder Kennwörter noch Tokens. Die Port-Abbildung
sollte nur während des Login-Vorgangs und nur im vertrauenswürdigen Heimnetz
aktiviert sein.

## Aktualisieren

- **Hermes Agent:** im Add-on-Terminal `hermes update` ausführen. Optional
  aktualisiert `auto_update_agent` beim Add-on-Start.
- **WebUI:** optional `auto_update_webui` aktivieren; dann wird der gepinnte
  WebUI-Checkout beim Start vom offiziellen `master`-Branch aktualisiert.
- **Add-on-Image:** eine neue Add-on-Version bauen und über das
  Home-Assistant-Add-on-Repository bereitstellen.

## Architektur

Das Add-on verwendet Home Assistant Ingress für WebUI und Terminal. Der
Terminal-Link sitzt direkt in der WebUI. Supervisor stellt den HA-Token
automatisch bereit; optional wird die MCP-Integration von Home Assistant in
Hermes registriert. `watch_entities` kann für die Hermes-Home-Assistant-
Plattform gesetzt werden.
