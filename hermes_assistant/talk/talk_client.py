"""Nextcloud Talk APIs used by a dedicated local account."""

import base64
import hashlib
import json
import re
from dataclasses import dataclass, field
from urllib.parse import quote, urlsplit

import aiohttp

TALK = "/ocs/v2.php/apps/spreed/api"
SHARES = "/ocs/v2.php/apps/files_sharing/api/v1/shares"
TOKEN = re.compile(r"[a-z0-9]{4,30}")
MAX_VOICE_BYTES = 20 * 1024 * 1024
PIPER_VOICES = {"JARVIS": "de_DE-thorsten-medium", "FRIDAY": "de_DE-eva_k-x_low"}
VOICE_SHARE_HINT = (
    "Talk-Sprachfreigabe: Die Chat-API liefert keinen lesbaren Dateianhang. "
    "Falls die Aufnahme im Browser abspielbar ist, prüfe den Dateizugriff des App-Passworts "
    "und ob dieselbe Freigabe unter Dateien für dieses Talk-Konto sichtbar ist. "
    "Sende die Aufnahme danach erneut als native Sprachnachricht."
)


class ServiceError(Exception):
    """An operator-facing error whose message contains no remote data."""


class InvalidVoice(Exception):
    """An attachment rejected before it can reach the agent."""


@dataclass(frozen=True)
class Settings:
    url: str
    user: str
    password: str = field(repr=False)
    allowed_users: frozenset
    allowed_rooms: frozenset
    api_key: str = field(repr=False)
    piper: tuple[str, int] | None = None
    persona: str = "JARVIS"
    voice: str = PIPER_VOICES["JARVIS"]
    calls: bool = False

    @classmethod
    def load(cls, options, *, persona="JARVIS", allow_http=False):
        friday = persona == "FRIDAY"
        prefix = "talk_friday_" if friday else "talk_"
        if options.get(prefix + "enabled") is not True:
            return None
        try:
            url = urlsplit(options.get("talk_url", "").strip())
            port = url.port
            schemes = {"https", "http"} if allow_http else {"https"}
            if (url.scheme not in schemes or not url.hostname or url.username is not None
                    or url.query or url.fragment or (port is not None and port < 1)):
                raise ValueError
        except (AttributeError, TypeError, ValueError):
            raise ServiceError("Talk-Konfiguration: eine HTTPS-URL ohne Zugangsdaten eingeben.") from None

        user = options.get(prefix + "username") or ""
        password = options.get(prefix + "app_password") or ""
        if (not user.strip() or user != user.strip() or ":" in user or "/" in user
                or "\\" in user or user in {".", ".."} or not password.strip()
                or any(ord(char) < 32 or ord(char) == 127 for char in user + password)):
            raise ServiceError("Talk-Anmeldung: Konto-ID und App-Passwort eingeben.")
        if friday and user == options.get("talk_username"):
            raise ServiceError("FRIDAY benötigt eine eigene Nextcloud-Konto-ID.")
        users = frozenset(s.strip() for s in options.get(prefix + "allowed_users", []) if s.strip())
        if friday and not users:
            users = frozenset(s.strip() for s in options.get("talk_allowed_users", []) if s.strip())
        rooms = frozenset(s.strip() for s in options.get(prefix + "allowed_rooms", []) if s.strip())
        if not users or user in users or any(not TOKEN.fullmatch(token) for token in rooms):
            raise ServiceError("Talk-Konfiguration: erlaubte Konto-IDs und ggf. gültige Raumtokens eingeben.")

        api_key = options.get("api_server_key") or ""
        if not options.get("api_server_enabled", True) or len(api_key) < 16:
            raise ServiceError("Talk benötigt den Hermes API Server mit einem gültigen API-Key.")

        piper = None
        endpoint = (options.get("talk_piper_endpoint") or "").strip()
        if endpoint:
            try:
                parsed = urlsplit(endpoint)
                if (parsed.scheme != "tcp" or not parsed.hostname or not parsed.port
                        or parsed.path or parsed.query or parsed.fragment or parsed.username is not None):
                    raise ValueError
                piper = (parsed.hostname, parsed.port)
            except ValueError:
                raise ServiceError("Piper-Konfiguration: Wyoming-Endpunkt als tcp://host:port eingeben.") from None
        voice = (options.get(prefix + "piper_voice") or PIPER_VOICES[persona]).strip()
        if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,100}", voice):
            raise ServiceError("Piper-Konfiguration: einen gültigen Wyoming-Stimmnamen eingeben.")
        return cls(url.geturl().rstrip("/"), user, password, users, rooms, api_key, piper, persona, voice,
                   options.get("talk_calls_enabled") is True)

    @property
    def scope(self):
        account = f"{self.url}\0{self.user}"
        if self.persona == "FRIDAY":
            account = "FRIDAY\0" + account
        return hashlib.sha256(account.encode()).hexdigest()


class TalkClient:
    def __init__(self, http, settings):
        self.http = http
        self.settings = settings
        credentials = f"{settings.user}:{settings.password}".encode()
        self.authorization = "Basic " + base64.b64encode(credentials).decode("ascii")

    async def ocs(self, method, path, *, component="Talk", params=None, data=None):
        try:
            async with self.http.request(
                method, self.settings.url + path,
                allow_redirects=False,
                params={"format": "json", **(params or {})}, data=data,
                headers={"Authorization": self.authorization, "OCS-APIRequest": "true",
                         "Accept": "application/json"},
            ) as response:
                if response.status == 304:
                    return [], response.headers
                if response.status in {401, 403} and component == "Talk-Anmeldung":
                    raise ServiceError("Talk-Anmeldung abgelehnt. Konto-ID und App-Passwort prüfen.")
                if response.status not in {200, 201}:
                    raise ServiceError(f"{component}: HTTP {response.status}.")
                ocs = (await response.json())["ocs"]
                if str(ocs["meta"]["statuscode"]) not in {"100", "200", "201"}:
                    raise ServiceError(f"{component}: OCS hat die Anfrage abgelehnt.")
                return ocs["data"], response.headers
        except (aiohttp.ClientError, TimeoutError, ValueError, TypeError, KeyError):
            raise ServiceError(f"{component}: API nicht erreichbar oder ungültige Antwort.") from None

    async def check_account(self):
        data, _ = await self.ocs("GET", "/ocs/v2.php/cloud/user", component="Talk-Anmeldung")
        if data.get("id") != self.settings.user:
            raise ServiceError("Talk-Anmeldung: Konto-ID stimmt nicht mit Nextcloud überein.")
        data, _ = await self.ocs("GET", "/ocs/v2.php/cloud/capabilities")
        features = data.get("capabilities", {}).get("spreed", {}).get("features", [])
        required = {"chat-v2", "chat-reference-id"}
        if not required.issubset(features):
            raise ServiceError("Talk: erforderliche Chat-Funktionen fehlen.")
        if self.settings.piper and "voice-message-sharing" not in features:
            raise ServiceError("Talk: Die Nextcloud-Instanz unterstützt keine nativen Voice Notes.")

    async def rooms(self):
        return list(await self.direct_messages())

    async def direct_messages(self):
        rooms, _ = await self.ocs("GET", f"{TALK}/v4/room", params={"noStatusUpdate": 1})
        return {
            room["token"]: room for room in rooms
            if room.get("type") == 1 and not room.get("remoteServer")
            and TOKEN.fullmatch(room.get("token", ""))
            and (not self.settings.allowed_rooms or room["token"] in self.settings.allowed_rooms)
        }

    async def peer(self, token):
        participants, _ = await self.ocs("GET", f"{TALK}/v4/room/{token}/participants")
        if len(participants) != 2 or any(p.get("actorType") != "users" for p in participants):
            return None
        users = {p.get("actorId") for p in participants}
        peers = users - {self.settings.user}
        if self.settings.user in users and len(peers) == 1 and peers <= self.settings.allowed_users:
            return next(iter(peers))
        return None

    async def call_participants(self, room):
        data, _ = await self.ocs("GET", f"{TALK}/v4/call/{room}", component="Talk-Anruf")
        if not isinstance(data, list):
            raise ServiceError("Talk-Anruf: Teilnehmerliste fehlt.")
        return data

    async def poll(self, room, cursor, *, timeout=25):
        data, headers = await self.ocs(
            "GET", f"{TALK}/v1/chat/{room}",
            params={"lookIntoFuture": 1, "lastKnownMessageId": cursor, "timeout": timeout,
                    "limit": 100, "setReadMarker": 0, "markNotificationsAsRead": 0},
        )
        try:
            entries = sorted(data, key=lambda entry: int(entry["id"]))
            # The last-given header can include invisible entries, e.g. expired messages.
            offset = max(cursor, int(headers.get("X-Chat-Last-Given", cursor)),
                         *(int(entry["id"]) for entry in entries))
            return entries, offset
        except (TypeError, ValueError, KeyError):
            raise ServiceError("Talk: ungültige Nachrichtenliste oder ungültiger Cursor.") from None

    def dav_url(self, path):
        return (f"{self.settings.url}/remote.php/dav/files/"
                f"{quote(self.settings.user, safe='')}/{quote(path.lstrip('/'), safe='/')}")

    async def download_voice(self, message, destination):
        path = voice_path(message)
        try:
            async with self.http.get(
                self.dav_url(path), headers={"Authorization": self.authorization}, allow_redirects=False,
            ) as response:
                if response.status in {403, 404}:
                    raise InvalidVoice(VOICE_SHARE_HINT)
                if response.status != 200:
                    raise ServiceError(f"Talk-WebDAV: HTTP {response.status} beim Download.")
                if response.content_length is not None and response.content_length > MAX_VOICE_BYTES:
                    raise InvalidVoice("Die Sprachnachricht ist größer als 20 MB.")
                size = 0
                with destination.open("wb") as stream:
                    async for chunk in response.content.iter_chunked(65536):
                        size += len(chunk)
                        if size > MAX_VOICE_BYTES:
                            raise InvalidVoice("Die Sprachnachricht ist größer als 20 MB.")
                        stream.write(chunk)
                if not size:
                    raise InvalidVoice("Die Sprachnachricht ist leer.")
        except (aiohttp.ClientError, TimeoutError):
            raise ServiceError("Talk-WebDAV: Download fehlgeschlagen.") from None

    async def has_reply(self, room, inbound, reference):
        # Look forward from the original message, including pages after a restart.
        cursor = inbound
        while True:
            entries, offset = await self.poll(room, cursor, timeout=0)
            if any(m.get("actorType") == "users" and m.get("actorId") == self.settings.user
                   and m.get("referenceId") == reference for m in entries):
                return True
            if offset == cursor:
                return False
            cursor = offset

    async def post_text(self, room, inbound, reference, body):
        if not await self.has_reply(room, inbound, reference):
            await self.ocs("POST", f"{TALK}/v1/chat/{room}",
                           data={"message": body, "referenceId": reference})

    async def post_voice(self, room, inbound, reference, audio):
        if await self.has_reply(room, inbound, reference):
            return
        folder = "Hermes-Talk"
        path = f"{folder}/Hermes-{reference[:24]}.mp3"
        try:
            for method, resource, expected, kwargs in (
                ("MKCOL", folder, {201, 405}, {}),
                ("PUT", path, {201, 204, 412},
                 {"data": audio, "headers": {"Content-Type": "audio/mpeg", "If-None-Match": "*"}}),
            ):
                async with self.http.request(
                    method, self.dav_url(resource), allow_redirects=False, data=kwargs.get("data"),
                    headers={"Authorization": self.authorization, **kwargs.get("headers", {})},
                ) as response:
                    if response.status not in expected:
                        raise ServiceError(f"Talk-WebDAV: HTTP {response.status} beim Upload.")
        except (aiohttp.ClientError, TimeoutError):
            raise ServiceError("Talk-WebDAV: Upload fehlgeschlagen.") from None
        # If the response is lost, the next attempt checks the chat again before sharing.
        await self.ocs("POST", SHARES, component="Talk-Sprachfreigabe",
                       data={"shareType": "10", "shareWith": room, "path": f"/{path}",
                             "referenceId": reference,
                             "talkMetaData": json.dumps({"messageType": "voice-message"})})


def voice_path(message):
    parameters = message.get("messageParameters")
    files = [p for p in parameters.values() if isinstance(p, dict) and p.get("type") == "file"] \
        if isinstance(parameters, dict) else []
    if len(files) != 1:
        raise InvalidVoice(VOICE_SHARE_HINT)
    attachment = files[0]
    try:
        permissions = int(attachment["permissions"])
        size = int(attachment["size"])
        path = attachment["path"]
        if (not permissions & 1 or not isinstance(path, str)
                or any(ord(c) < 32 or ord(c) == 127 for c in path) or "\\" in path
                or any(part in {"", ".", ".."} for part in path.removeprefix("/").split("/"))):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise InvalidVoice(VOICE_SHARE_HINT) from None
    if size < 1 or size > MAX_VOICE_BYTES:
        raise InvalidVoice("Die Sprachnachricht ist leer oder größer als 20 MB.")
    return path
