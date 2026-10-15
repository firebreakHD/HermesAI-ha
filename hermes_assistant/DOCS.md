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

## Lokaler gemeinsamer Browser (Add-on 2.0.5)

Das Add-on ergänzt Hermes' vorhandenen **Bot Screen**, keinen weiteren Agenten und keinen separaten MCP-Browser. Im Container werden TigerVNC, die Xfce-Kernkomponenten, Chromium und noVNC installiert. Der HA-Host bekommt keine Pakete, keinen Docker-Socket und keine privilegierte Browserfreigabe. Hermes' vorhandene Browserwerkzeuge und die manuelle Ansicht verwenden dasselbe native Profil.

Nach dem Update ist `browser_enabled` standardmäßig aktiv. Beim Start wird das von Hermes verwaltete `agent-browser`-Werkzeug vorbereitet und der native Bildschirm gestartet. Der Browserzugang steht in der WebUI oben unter **Werkzeuge → Browser**. **Setup-Terminal** liegt im selben eingeklappten Menü; die bisherigen schwebenden Buttons unten entfallen auch auf Mobilgeräten.

Bedienung:

1. Eine Browseraufgabe im Hermes-Chat stellen, z. B. „Öffne example.com in deinem sichtbaren lokalen Browser“.
2. **Werkzeuge → Browser** öffnen und den tatsächlichen Bildschirm ansehen.
3. Für Anmeldung oder CAPTCHA **Steuerung übernehmen** drücken. Hermes' native Browser- und Computer-Use-Werkzeuge werden durch die gemeinsame Lease gesperrt. Eigene Eingaben kommen nur vom aktuellen Besitzer am nativen RFB-Filter vorbei.
4. **An Hermes zurückgeben** drücken und im Chat **Weiter** schreiben. Hermes' native Übergabe beendet den wartenden Turn; die Webansicht sendet keinen heimlichen neuen Agentenauftrag. Der Folgeauftrag muss eine frische Seitenaufnahme verwenden.
5. **Pausieren** sperrt beide Eingaberichtungen. Bei verlorener Verbindung bleibt die manuelle Sperre bestehen. Nach erneutem Öffnen kann **Steuerung nach Verbindungsverlust zurückgeben** sie ausdrücklich aufheben.

Browserdaten liegen im nativen Profil unter `/data/hermes/bot-desktop/browser-profile`; Desktop und Chat verwenden denselben `HERMES_HOME`. Profileinstellungen und Logins bleiben im persistenten Add-on-Speicher erhalten, solange die Website sie nicht ablaufen lässt. Der gemeinsame Chromium-Starter verwendet `--restore-last-session`, um Tabs nach einem Neustart wiederherzustellen. Bereits abgeschickte Formularaktionen werden nicht als Arbeitsschritte wiederholt. Das native Bildschirm-Idle-Limit wird für diese Betriebsart auf 0 gesetzt, der native Schutz bei zu wenig freiem RAM bleibt aktiv. Für Desktop und Browser etwa 1–2 GB zusätzlich einplanen; mehrere große Websites können mehr benötigen.

Der kleine Webadapter nutzt direkt `tools.bot_desktop.runtime`, `lease` und `rfb_filter` der installierten Hermes-Version. Er läuft nur auf `127.0.0.1:9010`. Nginx lässt `/browser/` ausschließlich vom Supervisor-Ingress durch und setzt die interne Zugriffsmarkierung selbst. VNC hört auf Hermes' privatem Unix-Socket; es werden keine VNC-/CDP-Ports im LAN veröffentlicht. Browser-Zugriffslogs sind abgeschaltet, damit Viewer-Kennungen nicht im Log landen. Die Kontrolle ist wie beim nativen Hermes Bot Screen eine Werkzeugsperre, keine Isolation gegenüber beliebigen Shellprozessen desselben Containerbenutzers. Browserseiteninhalte sind keine neuen Benutzer- oder Systemanweisungen.

Die Integration setzt nur ihre eigenen Felder in `browser` und `bot_desktop`; Modellzugang, Home Assistant MCP und andere Konfiguration bleiben erhalten. Vorherige Werte dieser Felder werden privat in `.browser-original.json` gesichert. Bei `browser_enabled: false` werden unverändert gebliebene Integrationswerte wiederhergestellt. Nachträgliche eigene Änderungen bleiben erhalten. Neustart des Add-ons übernimmt die Option. Die zusätzlich eingebauten Systempakete bleiben im Image.

Abnahme: [BROWSER_PROMPT.txt](BROWSER_PROMPT.txt) enthält einen kopierbaren Testauftrag. Der Nutzer übernimmt einen echten Tab, ändert dessen Adresse und gibt die Kontrolle zurück. Danach muss Hermes nach „Weiter“ den aktuellen Zustand lesen und im selben Tab weiterarbeiten. Der zweite Test ist ein Add-on-Neustart mit Kontrolle von Profil und Tabs. Erst nach diesen Live-Tests ist die Einrichtung am Zielgerät bestätigt. Die lokalen Adaptertests verwenden einen simulierten nativen Bildschirm; sie ersetzen den Test am HA-Gerät nicht.

Fehlersuche: Bei fehlendem Bild zuerst Startprotokoll und `/data/hermes/bot-desktop/launcher.log` prüfen. Der native Bildschirm kann bei weniger als seinem konfigurierten freien RAM den Start verweigern. Die Schaltfläche **Bildschirm starten** wiederholt den Start, **Bild erneut verbinden** öffnet nur die Bildverbindung neu. `human_has_control` im Chat bedeutet, dass die manuelle Sperre noch aktiv ist. Bei fehlenden Browserwerkzeugen das Startprotokoll der `hermes pm install agent-browser`-Vorbereitung prüfen. Kein Cloud-Browser als stiller Ersatz.

Quellen: [Hermes Bot Screen](https://github.com/NousResearch/hermes-agent/blob/0e427d788d253630d38a3a51cd76849e73cd6925/website/docs/user-guide/features/bot-screen.md), [native Control Lease](https://github.com/NousResearch/hermes-agent/blob/0e427d788d253630d38a3a51cd76849e73cd6925/tools/bot_desktop/lease.py), [nativer RFB-Eingabefilter](https://github.com/NousResearch/hermes-agent/blob/0e427d788d253630d38a3a51cd76849e73cd6925/tools/bot_desktop/rfb_filter.py).

## Add-on-Optionen

| Option | Bedeutung |
| --- | --- |
| `timezone` | IANA-Zeitzone, z. B. `Europe/Vienna` |
| `enable_terminal` | Zeigt das integrierte Terminal in der WebUI an |
| `assistant_tools_enabled` | Aktiviert lokale Wetter-, Entfernungs-, Routen- und Kartenwerkzeuge ohne API-Schlüssel; standardmäßig aktiv |
| `auto_update_agent` | Führt `hermes update` beim Start aus |
| `auto_update_webui` | Aktualisiert den separaten WebUI-Checkout beim Start vom offiziellen `master`-Branch |
| `auto_configure_mcp` | Registriert Home Assistant MCP unter `/api/mcp` in Hermes |
| `api_server_enabled` | Aktiviert Hermes' OpenAI-kompatiblen API Server für JARVIS und andere Clients; der Gateway-Daemon für geplante Jobs läuft auch bei deaktivierter API |
| `api_server_key` | Starker API-Schlüssel für den Hermes API Server; denselben Wert in JARVIS eintragen |
| `desktop_backend_enabled` | Startet den offiziellen `hermes serve`-Server für Hermes Desktop; standardmäßig aus |
| `desktop_username` | Benutzername für die Desktop-Anmeldung |
| `desktop_password` | Passwort mit mindestens 16 Zeichen für die Desktop-Anmeldung; unabhängig vom API-Schlüssel |
| `homeassistant_token` | Optionaler eigener Long-Lived Access Token; leer nutzt den Supervisor-Token |
| `watch_entities` | Optionale Liste zu überwachender Entity-IDs |

Die MCP-Option setzt voraus, dass die Home-Assistant-Integration „Model
Context Protocol“ eingerichtet ist. Hermes und die WebUI teilen dieselben
persistenten Zugangsdaten, Sitzungen und Agent-Konfigurationen.

## Hermes Desktop vom PC verbinden (Add-on 2.0.6)

Die offizielle Desktop-App nutzt Hermes' JSON-RPC/WebSocket-Backend von `hermes serve`. Die OpenAI-kompatible API auf Port `8642` ist dafür nicht geeignet. Das Add-on kann den Desktop-Server auf internem Port `9119` dauerhaft starten; der Gateway-Daemon für geplante Jobs läuft daneben weiter.

1. In der Add-on-Konfiguration `desktop_backend_enabled` einschalten, `desktop_username` eintragen und ein eigenes `desktop_password` mit mindestens 16 Zeichen setzen. Diese Zugangsdaten sind unabhängig von `api_server_key`.
2. Unter **Netzwerk** dem Eintrag `9119/tcp` einen Host-Port zuweisen, z. B. `9119`. Die Desktop-Verbindung nur im vertrauenswürdigen Heimnetz oder über VPN nutzen; keine öffentliche Router-Portfreigabe einrichten.
3. Add-on neu starten. Im Startprotokoll muss „Starting authenticated Hermes Desktop backend on port 9119“ erscheinen. Bei Fehlern steht die Backend-Ausgabe unter `/data/hermes/logs/desktop-backend.log`.
4. In Hermes Desktop unter **Settings → Gateways → Remote gateway** die Adresse `http://<HOME-ASSISTANT-IP>:<DESKTOP-HOST-PORT>` eintragen, mit Benutzername und Passwort anmelden und die Verbindung speichern.

Der Signaturschlüssel für Desktop-Sitzungen wird einmalig unter `/data/hermes/.desktop-signing-secret` mit Dateirechten `0600` erzeugt. Damit bleiben Anmeldungen über Add-on-Neustarts hinweg gültig. Die Zugangsdaten werden weder in Startmeldungen noch in Shell-Argumenten ausgegeben. Ohne aktivierte Option läuft kein Desktop-Backend; ohne Host-Port-Zuweisung ist es vom PC nicht erreichbar. Das echte Anmelden und eine Chat-Nachricht in Hermes Desktop müssen nach dem Update am PC geprüft werden.

## Karten, Wege und Wetter ohne Schlüssel (Add-on 2.0.7)

`assistant_tools_enabled` registriert beim Start den lokalen MCP-Server `local_assistant`. Es sind keine Konten oder API-Schlüssel nötig:

- `mcp_local_assistant_route_and_maps` sucht Orte über OpenStreetMap Nominatim, berechnet eine Fahrstrecke über OSRM und liefert direkte Links für Google Maps, Apple Karten und OpenStreetMap. Ohne genannten Startpunkt nutzt das Tool automatisch Koordinaten aus Home Assistant `zone.home`.
- `mcp_local_assistant_weather_forecast` verwendet Open-Meteo für aktuelles Wetter und bis zu sieben Tage Vorhersage.

Beide Tools erzeugen unter `/data/hermes/generated` eine mobile HTML-Vorschau. Hermes Desktop kann sie mit dem zurückgegebenen `::preview`-Eintrag direkt im Chat anzeigen. Die bestehende Hermes-Aktivitätsanzeige stellt Aufruf und Ergebnis aller Tools bereits als aufklappbare Zeilen dar; Browser- und Bildschirmwerkzeuge erscheinen zusätzlich in Hermes Desktops nativer Screen-Ansicht. Die ältere Add-on-WebUI zeigt weiterhin die Textzusammenfassung und anklickbaren Kartenlinks, unterstützt aber nicht alle Desktop-Vorschau-Elemente.

Die verwaltete Skill-Datei `local-life-assistant` weist Hermes an, diese Tools bei passenden Fragen automatisch zu verwenden. [LIFE_ASSISTANT_PROMPT.txt](LIFE_ASSISTANT_PROMPT.txt) kann zusätzlich in eine bestehende Unterhaltung kopiert werden, um das gewünschte Antwortformat sofort festzulegen.

Späte Erinnerungen sind absichtlich an eine aktive Hermes-Desktop-Sitzung gebunden: Nur dort kann Hermes über seine Desktop-Werkzeuge aktuelle PC-Aktivität erkennen. Ein Heartbeat gehört technisch immer zu genau einer geöffneten Unterhaltung und wird daher nicht ungefragt global angelegt. Der Prompt enthält den fertigen Heartbeat-Befehl; nach ausdrücklicher Aktivierung prüft er stündlich, erinnert frühestens ab 23:30 Uhr, mit mindestens 90 Minuten Abstand und höchstens zweimal pro Nacht. Ohne sichere Aktivitätsdaten bleibt Hermes still.

Beeper Desktop besitzt zwar eine lokale API und einen MCP-Server, verlangt aber das manuelle Aktivieren unter **Beeper → Settings → Developers/Integrations** und läuft nur auf dem Windows-PC. Eine automatische Server-Integration ohne diesen Schritt wäre nicht funktionsfähig und ist deshalb nicht Bestandteil des Add-ons.

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

Die Browser-Bestätigung bedeutet zunächst nur, dass Hermes den Rückruf
empfangen hat. Im Terminal muss anschließend der Token-Austausch abgeschlossen
werden. Wird die Terminal-Verbindung zwischenzeitlich getrennt, öffnen Sie
das Setup-Terminal erneut: Ab Version 2.0.4 läuft dieselbe Shell mitsamt
dem wartenden Login weiter. Mit `hermes auth list` können Sie danach prüfen,
ob das Codex-Konto gespeichert wurde. Falls nicht, starten Sie den Login neu
und verwenden Sie die neue Anmelde-URL; alte Einmalcodes lassen sich nicht
erneut verwenden.

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
