# Nextcloud Talk mit Hermes auf Home Assistant OS

Stand 18. November 2026 · Technische Analyse und Implementierungsplan

## Entscheidung

Ein dediziertes Nextcloud-Konto namens Hermes ist die gemeinsame Identität für einen privaten Talk-DM, Sprachnachrichten und den späteren Anruf. Für Text und Sprachnachrichten ist der User-Modus von [smilinTux/hermes-nextcloud-talk](https://github.com/smilinTux/hermes-nextcloud-talk) die erste Wahl. Für Anrufe ist ein separater Call-Worker mit Headless Chromium der erste Prototyp. Der Bestand wurde anhand öffentlicher Quellen und der Repository-Dokumentation geprüft. Ein Ende-zu-Ende-Test steht aus.

## Textnachrichten

| Variante | Authentifizierung und Ablauf | Aufwand |
| --- | --- | --- |
| Talk-Bot | Admin registriert den Bot per `occ talk:bot:install` und aktiviert ihn pro Raum. Nextcloud sendet Webhooks. Der Empfänger prüft HMAC-SHA256 über Zufallswert und unveränderten Body. Beim Antwort-POST an `/ocs/v2.php/apps/spreed/api/v1/bot/{token}/message` wird Zufallswert plus Nachricht signiert. `replyTo` ist optional. | Gering. Nextcloud muss den Listener erreichen. Duplikate anhand von Raum- und Nachrichten-ID erkennen. Als Referenz dient [Cliff3c/hermes-nextcloud-talk](https://github.com/Cliff3c/hermes-nextcloud-talk). |
| Talk-User | Dediziertes Konto und Nextcloud-App-Passwort über HTTPS. Der Adapter wartet per `GET /chat/{token}` mit `lookIntoFuture=1` und verarbeitet neue Nachrichten sofort bei Eintreffen. `lastKnownMessageId` dient zum Nachholen. Die Antwort läuft über die Chat-API. | Gering. Kein eingehender Listener. Dieselbe Identität unterstützt DMs, freigegebene Dateien und den Call-Beitritt. Private DMs und erlaubte Absender zum Start explizit begrenzen. |

Quellen: [Talk Bot API](https://nextcloud-talk.readthedocs.io/en/stable/bots/) · [Talk Chat API](https://nextcloud-talk.readthedocs.io/en/stable/chat/) · [Hermes-Adapter und Changelog](https://github.com/smilinTux/hermes-nextcloud-talk/blob/master/CHANGELOG.md)

## Sprachnachrichten

1. Der User-Adapter erkennt die Voice Note, lädt die freigegebene Datei mit dem Agentenkonto per WebDAV und reicht sie in unterstützten Versionen als Hermes-`VOICE` weiter. Beim Download Dateigröße, Dauer, tatsächliches Format und Berechtigung begrenzen. Der dokumentierte Adapter begrenzt eingehende Dateien auf 20 MB.
2. Lokal mit [faster-whisper](https://github.com/SYSTRAN/faster-whisper) transkribieren. Auf x86 zunächst das mehrsprachige `small`-Modell mit CPU-`int8` testen. Das Transkript geht in dieselbe Hermes-Session wie der DM. Piper erzeugt das Antwortaudio. Bestehendes [Wyoming Piper](https://github.com/OHF-Voice/wyoming-piper) verwenden, wenn der Adapter oder ein kleiner lokaler Client den Dienst erreicht. Wyoming bleibt im internen Netz, weil das Protokoll keine eigene Authentifizierung oder Verschlüsselung bietet.
3. `send_voice` lädt die Audiodatei per WebDAV hoch und teilt sie über die OCS-Freigabe-API mit `shareType=10`, `shareWith=<room-token>` und `talkMetaData.messageType=voice-message`. WAV und MP3 auf dem iPhone prüfen. Bei unklarem Ergebnis nach einem Share-Timeout den Chat abgleichen, bevor erneut gesendet wird. Ein Webhook-Secret allein reicht für Upload und Freigabe nicht.

Quellen: [Talk-Dateifreigabe](https://nextcloud-talk.readthedocs.io/en/stable/chat/#share-a-file-to-the-chat) · [OpenClaw Talk als Referenz für native Voice Notes und Upload-Retries](https://docs.openclaw.ai/channels/nextcloud-talk) · [Wyoming-Protokoll](https://github.com/OHF-Voice/wyoming) · [Hermes Voice Mode](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/voice-mode.md)

## Live-Anruf

| Variante | Beleg und offene Arbeit |
| --- | --- |
| **Headless Chromium und Playwright** | [nextcloud-talk-notetaker](https://github.com/anentree/nextcloud-talk-notetaker) zeigt Beitritt per normalem Talk-Konto und den Empfang von WebRTC-Audiospuren. Join und Capture dienen als Vorlage. Der Prototyp muss laufende lokale Audioausgabe als Mikrofon einspeisen und über denselben Call zurückliefern. Chromium übernimmt die Talk-Client-Logik. Wartung mittel bis hoch bei Talk-UI-Änderungen. Die Gemini-Zusammenfassung des Notetakers ist für den Worker entbehrlich. |
| **Hermes-Call-Tools und skcall** | `call_join`, `call_leave` und `call_status` im [Hermes-Adapter](https://github.com/smilinTux/hermes-nextcloud-talk) steuern eine `systemd --user`-Unit. Das verlinkte [skcall-Repository](https://github.com/smilinTux/skcall) lieferte bei der Recherche 404. Medienpfad, Lizenz und reproduzierbarer Betrieb sind offen. |
| **Eigener WebRTC-Client** | [aiortc](https://github.com/aiortc/aiortc) und [Pion](https://github.com/pion/webrtc) liefern den Medientransport. Zusätzlich braucht der Client eine Talk-Raum-/Call-Session, versionsabhängige Signaling-Authentifizierung, SDP/ICE, Stream-Publikation, Media-Subscription und Reconnect. Der [HPB-Signaling-Server](https://github.com/strukturag/nextcloud-spreed-signaling) und die [Talk Call API](https://nextcloud-talk.readthedocs.io/en/stable/call/) sind die Referenzen. Höchster Implementierungs- und Wartungsaufwand. |
| **SIP oder Asterisk** | Die [offizielle Nextcloud-SIP-Bridge](https://nextcloud-talk.readthedocs.io/en/stable/quick-install/) setzt Talk Enterprise voraus. Ein freier Eigenbau müsste Talk-Signaling und SIP-/WebRTC-Audio koppeln. Asterisk allein kann keinem Talk-Call beitreten. |
| **Aufnahme, Untertitel und Chat-Bridges** | [Talk Recording](https://github.com/nextcloud/nextcloud-talk-recording) zeigt den Betrieb eines browserbasierten Aufnahme-Backends. [Live Transcription](https://github.com/nextcloud/live_transcription) zeigt Live-Transkription mit HPB. [Matterbridge](https://github.com/42wim/matterbridge) ist eine Chat-Bridge. Für die gesprochene Antwort im Call fehlt jeweils ein ausgehender Audiopfad. |

Der Call-Worker trennt die entfernte Audiospur von der lokalen Wiedergabe. Er wandelt den Eingang zu Mono-PCM für Whisper, erkennt Sprechpausen per VAD und übergibt das Transkript an Hermes. Piper-Audio geht über eine eigene virtuelle Mikrofonquelle im Chromium-Container zurück in den Call, etwa über PulseAudio. Der bestehende [Hermes-Discord-Adapter](https://github.com/NousResearch/hermes-agent/blob/main/plugins/platforms/discord/adapter.py) zeigt die Regeln für Sprecherfilter, Puffer und Pausenerkennung. Talk behält sein eigenes Signaling und Login.

Für automatisches Annehmen dient zunächst `hasCall` im dedizierten DM als Hinweis. Vor dem Beitritt den erlaubten Teilnehmer prüfen und eigene oder bereits bearbeitete Anrufe ausschließen. Zielwerte für einen kurzen Turn ohne Tools sind unter fünf Sekunden bis zum Beitritt im LAN und zwei bis fünf Sekunden vom Satzende bis zum ersten Antwortaudio. Das sind Abnahmeziele, keine Messwerte. Pausenerkennung, Whisper, Hermes und erstes Piper-Audio einzeln instrumentieren. WLAN, VPN und Mobilfunk getrennt testen. Je nach NAT und Erreichbarkeit den [TURN-Pfad](https://nextcloud-talk.readthedocs.io/en/stable/TURN/) und bei HPB den WebSocket-Endpunkt prüfen.

## Architektur und HAOS

- **Chat und Sprachnachrichten:** Talk-App → Nextcloud → Hermes-Talk-Adapter → vorhandenes Hermes-Gateway. Whisper und Piper lokal. Bei Versionsproblemen zuerst Adapter-Commit und Hermes-Build abgleichen. Als Alternative kann eine kleine Bridge dieselben Talk-APIs verwenden und Hermes über HTTP ansprechen.
- **Live:** Talk-WebRTC ↔ Chromium-Worker → VAD/Whisper → Hermes → Piper → virtuelles Chromium-Mikrofon. Der Worker läuft als separate HAOS-App und verwendet bei aktivierter API die im [Projekt-README](../README.md#api-und-netzwerk) dokumentierte interne Basisadresse `http://<REPO-ID>-hermes-assistant:8642`. Der API-Schlüssel authentifiziert den Worker lokal per Bearer-Token. `/v1/chat/completions` oder `/v1/responses` anhand des installierten Builds auswählen. Für Calls zunächst eine eigene Session festlegen, gemeinsamen DM- und Call-Verlauf erst nach geprüftem Mapping aktivieren.
- **Betrieb:** Chromium, virtuelle Audioquelle und App-Lebenszyklus innerhalb des separaten Containers. Kein Supervisor- oder Docker-Socket-Zugriff erforderlich. Zuerst einen Call gleichzeitig mit CPU und RAM messen. Vorhandenen HPB oder TURN weiterverwenden, falls vorhanden. Die Spracherkennung und Synthese bleiben lokal. Hermes kann den bestehenden Codex-/ChatGPT-Login gemäß dessen Kontingent nutzen.

Quellen: [Hermes API](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server) · [Hermes-Modellanbieter](https://hermes-agent.nousresearch.com/docs/integrations/providers) · [HAOS-App-Konfiguration](https://contributors.home-assistant.io/apps/reference/configuration/)

## Umsetzung und Abnahme für Codex

| Phase | Aufgabe | Abnahme |
| --- | --- | --- |
| 0. Bestand | Hermes, Nextcloud und Talk samt Capabilities, HPB/TURN und Erreichbarkeit der Wyoming-Dienste erfassen. Adapter-Commit auf dem tatsächlich installierten Hermes-Build prüfen und pinnen. | Kompatible Versionen und interne Endpunkte sind dokumentiert. |
| 1. Text | Agentenkonto mit App-Passwort und erlaubtem Benutzer an den User-Adapter im privaten Test-DM anbinden. Cursor und Duplikaterkennung prüfen. | Zwei Nachrichten behalten Kontext. Nach Neustart und Reconnect wird jede neue Nachricht einmal beantwortet. |
| 2. Voice Notes | WebDAV, lokales Whisper, Hermes, Piper und native Talk-Dateifreigabe verbinden. | Eine iPhone-Sprachnachricht in österreichischem Deutsch erhält eine abspielbare Antwort. Längere Aufnahme und simulierten Upload-Timeout prüfen. |
| 3. WebRTC-Prototyp | Headless-Worker dem Test-DM beitreten lassen. Eingehenden Testton im Worker erkennen und einen anderen lokalen Testton über das virtuelle Mikrofon zurücksenden. | Beide Richtungen, Auflegen und erneuter Anruf am iPhone im WLAN funktionieren. |
| 4. Live-Dialog | VAD, Whisper, Hermes und Piper ergänzen. Erst Redewechsel testen, dann Ausgabe bei erneutem Sprechen abbrechen. Automatischen Beitritt auf den erlaubten DM und Anrufer beschränken. | Anruf aus der Talk-App annehmen, zwei kurze Fragen beantworten, sauber auflegen. Zeiten je Stufe erfassen. |
| 5. HAOS | Call-Worker als App paketieren, Abhängigkeiten pinnen und persistente Konfiguration, Healthcheck und Wiederanlauf ergänzen. | Wiederanlauf sowie Anrufe über WLAN, vorhandenes VPN und den vorgesehenen Mobilfunkzugang prüfen. Last von HAOS und Call-Worker festhalten. |
