"""Run one supervised Talk contact alongside the existing Hermes gateway."""

import asyncio
import hashlib
import json
import logging
import os
import signal
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

import aiohttp

from talk_audio import PiperError, Whisper, piper_audio
from talk_client import InvalidVoice, ServiceError, Settings, TalkClient, VOICE_SHARE_HINT

LOG = logging.getLogger("hermes-talk")
HERMES_URL = "http://127.0.0.1:8642"
DISCOVERY_SECONDS = 5
MAX_REPLY = 8000
PERSONAS = {
    "JARVIS": "Du bist JARVIS, ein ruhiger, präziser und diskreter persönlicher Assistent.",
    "FRIDAY": "Du bist FRIDAY, eine direkte, freundliche und pragmatische persönliche Assistentin.",
}
GERMAN = "Antworte immer in natürlichem Deutsch, gerne österreichisch formuliert, auch bei englischer Eingabe."


class State:
    def __init__(self, path, scope):
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA secure_delete=ON")
        self.db.execute("CREATE TABLE IF NOT EXISTS accounts (scope TEXT PRIMARY KEY, since INTEGER NOT NULL)")
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS rooms (
                scope TEXT, room TEXT, cursor INTEGER NOT NULL DEFAULT 0,
                message_id INTEGER, answer TEXT, voice INTEGER, audio BLOB, PRIMARY KEY (scope, room)
            )
        """)
        self.scope = scope
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO accounts VALUES (?, ?)", (scope, int(time.time())))
        self.since = self.db.execute("SELECT since FROM accounts WHERE scope=?", (scope,)).fetchone()[0]

    def load(self, room):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO rooms (scope, room) VALUES (?, ?)", (self.scope, room))
        return self.db.execute("SELECT cursor, message_id, answer, voice, audio FROM rooms WHERE scope=? AND room=?",
                               (self.scope, room)).fetchone()

    def draft(self, room, message_id, answer, voice, audio=None):
        with self.db:
            self.db.execute("UPDATE rooms SET message_id=?, answer=?, voice=?, audio=? WHERE scope=? AND room=?",
                            (message_id, answer, voice, audio, self.scope, room))

    def advance(self, room, cursor):
        with self.db:
            self.db.execute("UPDATE rooms SET cursor=?, message_id=NULL, answer=NULL, voice=NULL, audio=NULL WHERE scope=? AND room=?",
                            (cursor, self.scope, room))


def message_kind(message, room, peer, since):
    if (message.get("token") != room or message.get("actorType") != "users"
            or message.get("actorId") != peer or message.get("timestamp", 0) < since):
        return None
    kind = message.get("messageType")
    if kind == "voice-message":
        return "voice"
    body = message.get("message")
    if message.get("systemMessage") == "file_shared" or (
        kind == "comment" and isinstance(body, str) and (
            body.strip() == "{file}" or body.lstrip().startswith((
                "*{actor} shared a file which is no longer available*",
                "*{actor} hat eine Datei geteilt, die nicht mehr vorhanden ist*",
            ))
        )
    ):
        return "file"
    if kind == "comment" and not message.get("systemMessage") and isinstance(body, str) and body.strip():
        parameters = message.get("messageParameters")
        if isinstance(parameters, dict) and any(
            isinstance(value, dict) and value.get("type") == "file" for value in parameters.values()
        ):
            return "file"
        return "text"
    return None


def identifier(*parts):
    return hashlib.sha256(":".join(map(str, parts)).encode()).hexdigest()


class Hermes:
    def __init__(self, http, settings):
        self.http = http
        self.settings = settings

    async def answer(self, session, turn, prompt, voice):
        instructions = f"{PERSONAS[self.settings.persona]} {GERMAN}"
        if voice:
            instructions += " Antworte kurz und in gut vorlesbaren Sätzen."
        messages = [{"role": "system", "content": instructions}, {"role": "user", "content": prompt}]
        try:
            async with self.http.post(
                HERMES_URL + "/v1/chat/completions", json={"messages": messages},
                headers={"Authorization": f"Bearer {self.settings.api_key}", "X-Hermes-Session-Id": session,
                         "Idempotency-Key": turn},
                timeout=aiohttp.ClientTimeout(total=300), allow_redirects=False,
            ) as response:
                if response.status != 200:
                    raise ServiceError(f"Hermes-API: HTTP {response.status}. Gateway und Modellanmeldung prüfen.")
                if response.headers.get("X-Hermes-Session-Id") != session:
                    raise ServiceError("Hermes-API: Die installierte Agent-Version unterstützt den DM-Kontext nicht.")
                result = (await response.json())["choices"][0]["message"]["content"]
                if not isinstance(result, str) or not result.strip():
                    raise ValueError
                return result.strip()[:MAX_REPLY]
        except (aiohttp.ClientError, TimeoutError, ValueError, TypeError, IndexError, KeyError):
            raise ServiceError("Hermes-API: Gateway nicht erreichbar oder keine verwendbare Antwort.") from None


class Bridge:
    def __init__(self, settings, state, talk, hermes, whisper):
        self.settings = settings
        self.state = state
        self.talk = talk
        self.hermes = hermes
        self.whisper = whisper

    async def deliver(self, room, msg_id, answer, voice, audio):
        if voice:
            await self.talk.post_voice(
                room, msg_id, identifier(self.settings.scope, room, msg_id, "voice"), audio,
            )
        else:
            for index in range(0, len(answer), 1900):
                await self.talk.post_text(
                    room, msg_id, identifier(self.settings.scope, room, msg_id, "text", index),
                    answer[index:index + 1900],
                )

    async def reply(self, room, message, kind, draft):
        msg_id = int(message["id"])
        answer, voice, audio = draft
        if answer is None:
            voice = kind == "voice"
            try:
                if kind == "file":
                    raise InvalidVoice(VOICE_SHARE_HINT)
                if voice:
                    if not self.settings.piper:
                        raise InvalidVoice("Sprachnachrichten benötigen einen konfigurierten Wyoming-Piper-Dienst.")
                    with tempfile.TemporaryDirectory(prefix="hermes-talk-") as temp:
                        path = Path(temp) / "input"
                        await self.talk.download_voice(message, path)
                        prompt = await self.whisper.transcribe(path)
                    if not prompt:
                        raise InvalidVoice("In der Sprachnachricht wurde keine Sprache erkannt.")
                else:
                    prompt = message["message"]
                session = "talk-" + identifier(self.settings.scope, room)[:32]
                answer = await self.hermes.answer(
                    session, identifier(session, msg_id), prompt, voice,
                )
            except InvalidVoice as error:
                answer, voice = str(error), False
                LOG.warning("%s", error)
            self.state.draft(room, msg_id, answer, voice)

        if voice and audio is None:
            try:
                if not self.settings.piper:
                    raise PiperError("Piper-Konfiguration: Wyoming-Endpunkt fehlt.")
                audio = await piper_audio(self.settings.piper, answer, self.settings.voice)
            except PiperError as error:
                LOG.warning("%s", error)
                answer = f"Sprachausgabe fehlgeschlagen. Hier ist die Antwort als Text:\n\n{answer}"
                voice = False
            self.state.draft(room, msg_id, answer, voice, audio)
        await self.deliver(room, msg_id, answer, voice, audio)

    async def room_loop(self, room, peer):
        delay = 1
        while True:
            try:
                await self.process_batch(room, peer)
                delay = 1
            except ServiceError as error:
                LOG.warning("%s Erneuter Versuch in %d s.", error, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)

    async def process_batch(self, room, peer):
        cursor, pending_id, *draft = self.state.load(room)
        entries, offset = await self.talk.poll(room, cursor)
        if entries and await self.talk.peer(room) != peer:
            raise ServiceError("Talk: Teilnehmerliste hat sich geändert.")
        for message in entries:
            msg_id = int(message["id"])
            if msg_id <= cursor:
                continue
            kind = message_kind(message, room, peer, self.state.since)
            if kind:
                await self.reply(room, message, kind, draft if msg_id == pending_id else (None, None, None))
            self.state.advance(room, msg_id)
            cursor, pending_id = msg_id, None
        if offset > cursor:
            self.state.advance(room, offset)

    async def run(self):
        await self.talk.check_account()
        LOG.info("Mit Nextcloud Talk verbunden. Warte auf erlaubte private DMs.")
        workers = {}
        try:
            while True:
                try:
                    rooms = set(await self.talk.rooms())
                except ServiceError as error:
                    LOG.warning("%s Raumsuche wird wiederholt.", error)
                    await asyncio.sleep(DISCOVERY_SECONDS)
                    continue
                for room in set(workers) - rooms:
                    task = workers.pop(room)
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                for room in rooms:
                    if room not in workers:
                        try:
                            peer = await self.talk.peer(room)
                        except ServiceError as error:
                            LOG.warning("%s Teilnehmerprüfung wird wiederholt.", error)
                            continue
                        if peer:
                            workers[room] = asyncio.create_task(self.room_loop(room, peer))
                    elif workers[room].done():
                        workers.pop(room).result()
                await asyncio.sleep(DISCOVERY_SECONDS)
        finally:
            for task in workers.values():
                task.cancel()
            await asyncio.gather(*workers.values(), return_exceptions=True)


async def main(persona):
    config_file = Path("/data/options.json")
    root = Path("/data/hermes/talk")
    try:
        settings = Settings.load(json.loads(config_file.read_text()), persona=persona)
        if settings is None:
            return 0
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        database = "delivery.sqlite3" if persona == "JARVIS" else "delivery-friday.sqlite3"
        state = State(root / database, settings.scope)
    except (OSError, ValueError, TypeError, sqlite3.Error):
        LOG.error("Talk: Konfiguration oder lokaler Nachrichtenspeicher konnte nicht geöffnet werden.")
        return 2
    except ServiceError as error:
        LOG.error("%s", error)
        return 2

    delay = 5
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=45), cookie_jar=aiohttp.DummyCookieJar(),
    ) as http:
        bridge = Bridge(settings, state, TalkClient(http, settings), Hermes(http, settings),
                        Whisper(root / "models"))
        while True:
            try:
                await bridge.run()
            except ServiceError as error:
                LOG.warning("%s Erneuter Verbindungsversuch in %d s.", error, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)


if __name__ == "__main__":
    os.umask(0o077)
    persona = "FRIDAY" if sys.argv[1:] == ["FRIDAY"] else "JARVIS"
    logging.basicConfig(level=logging.INFO, format=f"[Nextcloud Talk {persona}] %(message)s")
    # Keep request URLs, server responses, model text and audio out of worker logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    logging.getLogger("faster_whisper").setLevel(logging.WARNING)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        sys.exit(asyncio.run(main(persona)))
    except Exception:
        LOG.error("Talk: Worker unerwartet beendet. Konfiguration und Add-on-Version prüfen.")
        sys.exit(1)
