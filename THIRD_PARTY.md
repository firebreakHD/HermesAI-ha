# Verwendete Projekte

Das Add-on lädt beim Image-Build die folgenden Projekte. Ihre Quelltexte
werden nicht in diesem Git-Repository abgelegt.

| Projekt | Version im initialen Image | Lizenz |
| --- | --- | --- |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) | Commit `0e427d788d253630d38a3a51cd76849e73cd6925` | [MIT](https://github.com/NousResearch/hermes-agent/blob/main/LICENSE) |
| [Hermes WebUI](https://github.com/nesquena/hermes-webui) | Tag `v0.52.76` | [MIT](https://github.com/nesquena/hermes-webui/blob/master/LICENSE) |
| [ttyd](https://github.com/tsl0922/ttyd) | `1.7.7` | [MIT](https://github.com/tsl0922/ttyd/blob/1.7.7/LICENSE) |

Die Lizenzen von Hermes Agent und WebUI bleiben in ihren Checkouts im Image.
Die ttyd-Lizenz wird nach `/usr/share/doc/ttyd/LICENSE` kopiert.

Der Nextcloud-Talk-Worker hat eine vom Hermes-Agent getrennte Python-Umgebung.
Die Versionen seiner Python-Pakete stehen in
[`hermes_assistant/talk/requirements.txt`](hermes_assistant/talk/requirements.txt).
Direkte Abhängigkeiten sind [aiohttp](https://github.com/aio-libs/aiohttp) (Apache-2.0),
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) (MIT) und die
[Wyoming-Python-Bibliothek](https://github.com/OHF-Voice/wyoming) (MIT).
Die Lizenzdateien der Wheels bleiben in der Umgebung. Das
[Whisper-Modell small](https://huggingface.co/Systran/faster-whisper-small)
(MIT) wird beim ersten Sprachturn in der im Code festgelegten Revision bezogen.

Die Implementierung verwendet die öffentlichen Talk-APIs. Der
[User-Adapter](https://github.com/smilinTux/hermes-nextcloud-talk/tree/265228b80a7ef59a12aa2402eabeec6d4cb3c1ad)
(MIT) wurde als Referenz geprüft. Sein Download prüft die Bytegrenze nach
dem Puffern. Die Transkription hängt von der STT-Einstellung des Hermes-Agenten
ab. Der Add-on-Worker verwendet einen begrenzten Download und eine eigene
lokale STT-Konfiguration. Der
[Talk-Notetaker](https://github.com/anentree/nextcloud-talk-notetaker/tree/46eabd4c17ed3ea15f8525b797e2cc26aad869a6)
(AGPL-3.0) dient als Referenz für Browserbeitritt und Empfang von WebRTC-Audio.
Keiner der beiden Adapter wird in das Image kopiert.

Der optionale Call-Worker verwendet [Playwright](https://github.com/microsoft/playwright-python)
(Apache-2.0), das Debian-Paket Chromium und
[webrtcvad-wheels](https://github.com/daanzu/py-webrtcvad-wheels) (MIT,
mit BSD-lizenziertem WebRTC-VAD-Code).
