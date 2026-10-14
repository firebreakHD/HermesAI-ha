# Hermes Assistant

Hermes Agent läuft im selben Add-on wie die bekannte Hermes-WebUI und das
Setup-Terminal. Beide sind über den Hermes-Agent-Eintrag in der HA-Sidebar
erreichbar. Der Agent-Code basiert auf dem offiziellen NousResearch-Repository;
Agent-Version und WebUI-Tag sind im Dockerfile für reproduzierbare Builds
festgelegt.

## Erste Einrichtung

1. Add-on-Optionen speichern und das Add-on starten.
2. Hermes Agent über die Sidebar öffnen.
3. Im Terminal `hermes setup` ausführen und Modellanbieter sowie Zugangsdaten
   einrichten.
4. Ein Codex-Konto kann im Terminal mit
   `hermes auth add openai-codex --browser` hinzugefügt werden. Für den
   Browser-Rückruf siehe den Abschnitt „Codex-Browser-Login“ weiter unten.

## Add-on-Optionen

| Option | Bedeutung |
| --- | --- |
| `timezone` | IANA-Zeitzone, z. B. `Europe/Vienna` |
| `enable_terminal` | Zeigt das integrierte Terminal in der WebUI an |
| `auto_update_agent` | Führt `hermes update` beim Start aus |
| `auto_update_webui` | Aktualisiert den separaten WebUI-Checkout beim Start vom offiziellen `master`-Branch |
| `auto_configure_mcp` | Registriert Home Assistant MCP unter `/api/mcp` in Hermes |
| `api_server_enabled` | Aktiviert Hermes' OpenAI-kompatiblen API Server für JARVIS und andere Clients; der Gateway-Daemon für geplante Jobs läuft auch bei deaktivierter API |
| `api_server_key` | Starker API-Schlüssel für den Hermes API Server; denselben Wert in JARVIS eintragen |
| `homeassistant_token` | Optionaler eigener Long-Lived Access Token; leer nutzt den Supervisor-Token |
| `watch_entities` | Optionale Liste zu überwachender Entity-IDs |

Die MCP-Option setzt voraus, dass die Home-Assistant-Integration „Model
Context Protocol“ eingerichtet ist. Hermes und die WebUI teilen dieselben
persistenten Zugangsdaten, Sitzungen und Agent-Konfigurationen.

## JARVIS und Hermes API

Der offizielle Hermes API Server läuft auf Port `8642` und ist im Add-on-
Netzwerk veröffentlicht. Bei einer Port-Kollision lässt sich der Host-Port in
der Home-Assistant-Netzwerk-Konfiguration des Add-ons ändern; der interne
Hermes-Port bleibt `8642`.

1. Einen starken Wert in `api_server_key` eintragen. Unter Windows lässt er
   sich mit PowerShell erzeugen:

   ```powershell
   $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
   $bytes = New-Object byte[] 32
   $rng.GetBytes($bytes)
   [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
   $rng.Dispose()
   ```
2. Add-on-Optionen speichern und Hermes Assistant neu starten.
3. Im JARVIS-Add-on als Basisadresse `http://<REPO-ID>-hermes-assistant:8642`
   eintragen (ohne `/v1`) und denselben API-Schlüssel setzen. Bei einer lokalen
   Installation ist die Repository-ID `local`; bei Installation aus GitHub
   zeigt Home Assistant die generierte Repository-ID an.

Für Clients außerhalb des Home-Assistant-Add-on-Netzes verwendest du
`http://<HOME-ASSISTANT-IP>:<HOST-PORT>`. Der Host-Port ist standardmäßig
`8642` und lässt sich bei Kollision in der Netzwerk-Konfiguration des Add-ons
ändern. Die interne Add-on-Adresse folgt dem von Home Assistant dokumentierten
Schema `{REPO}_{SLUG}` als DNS-Name mit Bindestrichen.

## Gateway und geplante Jobs

Der Gateway-Daemon startet mit dem Add-on und führt geplante Hermes-Jobs aus
dem Tasks-Bereich aus. Ist `api_server_enabled` aktiviert, prüft die WebUI
seinen Zustand über `http://127.0.0.1:8642/health/detailed` mit dem
konfigurierten API-Schlüssel. Der bisherige WebUI-Chat bleibt im selben
Bedienmodus. Im Add-on-Terminal zeigt `hermes gateway status` den
Daemon-Zustand an. Gateway-Ausgaben stehen in
`/data/hermes/logs/gateway.log`; der API-Schlüssel wird dort nicht
protokolliert.

## Codex-Browser-Login

Der Browser-Flow nutzt OpenAIs OAuth-Rückruf `localhost:1455`. Hermes wartet
im Add-on-Container auf einen HTTP-Aufruf; die Rückgabe-URL in das wartende
Terminal einzufügen reicht nicht. Ordnen Sie in der Netzwerk-Konfiguration
des Add-ons `1456/tcp` dem Host-Port `1456` zu und starten Sie das Add-on neu.
Dann im Add-on-Terminal:

```sh
hermes auth add openai-codex --browser
```

Öffnen Sie die angezeigte Anmelde-URL auf dem Browser-PC. Falls der Browser
danach bei `http://localhost:1455/auth/callback?code=...&state=...` einen
Verbindungsfehler zeigt, ersetzen Sie in der Adresszeile **nur**
`localhost:1455` durch `<HOME-ASSISTANT-IP>:1456` und öffnen Sie die
geänderte URL. Pfad und Abfrage müssen erhalten bleiben.

Alternativ können Sie vor dem Login auf dem Browser-PC das Skript
`codex-browser-callback-proxy.ps1` aus dem Repository starten; es leitet den
Rückruf automatisch weiter. Nach erfolgreichem Login das Skript beenden und
die Port-Zuordnung wieder entfernen. Die Rückgabe-URL mit ihrem einmaligen
Anmeldecode nicht teilen. Der Browser-PC und Home Assistant müssen sich im
selben vertrauenswürdigen LAN befinden.

## Persistenz und Updates

Hermes-Konfiguration, Modellzugänge, Authentifizierung, Sitzungen, Erinnerungen
und installierter Agent-Checkout liegen unter `/data/hermes`. `hermes update`
aktualisiert diesen Checkout und bleibt über Add-on-Neustarts erhalten. Das
Add-on-Image enthält einen festgelegten Hermes-Stand als Seed für die erste
Installation.
