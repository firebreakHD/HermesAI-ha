import asyncio
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "talk"))

from talk_audio import PiperError, decode_voice, piper_pcm
from talk_client import InvalidVoice, ServiceError, Settings, TalkClient, voice_path
from talk_worker import Bridge, Hermes, State, message_kind

AUTHORIZATION = "Basic aGVybWVzOmV4YW1wbGUtYXBwLXBhc3N3b3Jk"
OPTIONS = {
    "talk_enabled": True,
    "talk_url": "https://nextcloud.example.invalid",
    "talk_username": "hermes",
    "talk_app_password": "example-app-password",
    "talk_allowed_users": ["Marcel"],
    "talk_allowed_rooms": ["abcd1234"],
    "api_server_key": "example-hermes-key",
    "talk_piper_endpoint": "tcp://local-piper:10200",
}
FRIDAY = {
    "talk_friday_enabled": True,
    "talk_friday_username": "friday",
    "talk_friday_app_password": "friday-app-password",
}
VOICE_FILE = {"type": "file", "path": "Talk/note.mp3", "permissions": "1", "size": "1500"}


def message(message_id=1, **kwargs):
    return {"token": "abcd1234", "actorType": "users", "actorId": "Marcel", "messageType": "comment",
            "systemMessage": "", "message": "Guten Morgen", "timestamp": 2_000_000_000,
            "id": message_id, **kwargs}


def ocs(data):
    return web.json_response({"ocs": {"meta": {"statuscode": 200}, "data": data}})


class SettingsTests(unittest.TestCase):
    def test_friday_is_opt_in_with_independent_credentials_and_room_limits(self):
        self.assertIsNone(Settings.load(OPTIONS, persona="FRIDAY"))
        options = {**OPTIONS, **FRIDAY, "talk_calls_enabled": True}
        jarvis = Settings.load(options)
        friday = Settings.load(options, persona="FRIDAY")
        self.assertEqual(jarvis.user, "hermes")
        self.assertEqual(friday.user, "friday")
        self.assertNotIn(FRIDAY["talk_friday_app_password"], repr(friday))
        self.assertEqual(jarvis.piper, friday.piper)
        self.assertTrue(jarvis.calls and friday.calls)
        self.assertEqual(jarvis.voice, "de_DE-thorsten-medium")
        self.assertEqual(friday.voice, "de_DE-eva_k-x_low")
        self.assertEqual(friday.allowed_users, {"Marcel"})
        self.assertEqual(friday.allowed_rooms, set())
        restricted = Settings.load({**options, "talk_friday_allowed_users": ["SomeoneElse"],
                                    "talk_friday_allowed_rooms": ["otherdm"]}, persona="FRIDAY")
        self.assertEqual(restricted.allowed_users, {"SomeoneElse"})
        self.assertEqual(restricted.allowed_rooms, {"otherdm"})
        with self.assertRaisesRegex(ServiceError, "eigene Nextcloud-Konto-ID"):
            Settings.load({**options, "talk_friday_username": "hermes"}, persona="FRIDAY")

    def test_defaults_and_validation(self):
        self.assertIsNone(Settings.load({}))
        settings = Settings.load(OPTIONS)
        self.assertEqual(settings.piper, ("local-piper", 10200))
        self.assertNotIn(OPTIONS["talk_app_password"], repr(settings))
        self.assertNotIn(OPTIONS["api_server_key"], repr(settings))
        for update in (
            {"talk_allowed_users": []}, {"talk_allowed_users": ["hermes"]},
            {"talk_allowed_rooms": ["../../webdav"]}, {"talk_app_password": ""},
            {"talk_url": "http://nextcloud.example.invalid"}, {"talk_url": "https://user:secret@host"},
            {"api_server_enabled": False}, {"talk_piper_endpoint": "http://local-piper:10200"},
        ):
            with self.subTest(update=update), self.assertRaises(ServiceError):
                Settings.load({**OPTIONS, **update})

    def test_sender_and_room_filter(self):
        self.assertEqual(message_kind(message(), "abcd1234", "Marcel", 0), "text")
        voice = message(messageType="voice-message", systemMessage="file_shared")
        self.assertEqual(message_kind(voice, "abcd1234", "Marcel", 0), "voice")
        for changed in (
            {"actorId": "hermes"}, {"actorId": "marcel"}, {"actorType": "federated_users"},
            {"token": "anotherroom"}, {"timestamp": 0},
            {"messageType": "system"}, {"messageType": "command"},
        ):
            self.assertIsNone(message_kind(message(**changed), "abcd1234", "Marcel", 1))

    def test_voice_share_validation(self):
        self.assertEqual(voice_path({"messageParameters": {"file": VOICE_FILE}}), "Talk/note.mp3")
        for update in (
            {"permissions": "0"}, {"path": "https://other.example/a"}, {"path": "Talk/../file"},
            {"path": "Talk\\file"}, {"size": "0"}, {"size": str(21 * 1024 * 1024)},
        ):
            with self.subTest(update=update), self.assertRaises(InvalidVoice):
                voice_path({"messageParameters": {"file": {**VOICE_FILE, **update}}})

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg tools required")
    def test_actual_audio_format_and_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "test.wav"
            for length in (1, 181):
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                                f"sine=duration={length}", str(audio)], check=True)
                if length == 1:
                    self.assertEqual(len(decode_voice(audio)), 32000)
                else:
                    with self.assertRaises(InvalidVoice):
                        decode_voice(audio)
            audio.write_text("not audio")
            with self.assertRaises(InvalidVoice):
                decode_voice(audio)


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_upgrade_keeps_existing_scope_cursor_and_dm_session(self):
        legacy_scope = hashlib.sha256(b"https://nextcloud.example.invalid\x00hermes").hexdigest()
        legacy_session = "talk-" + hashlib.sha256(f"{legacy_scope}:abcd1234".encode()).hexdigest()[:32]
        talk, hermes = AsyncMock(), AsyncMock()
        talk.peer.return_value = "Marcel"
        talk.poll.return_value = ([message(1), message(2)], 2)
        hermes.answer.return_value = "Guten Morgen!"
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "delivery.sqlite3"
            legacy = State(database, legacy_scope)
            legacy.load("abcd1234")
            legacy.advance("abcd1234", 1)
            legacy.db.close()
            jarvis = Settings.load(OPTIONS)
            state = State(database, jarvis.scope)
            await Bridge(jarvis, state, talk, hermes, None).process_batch("abcd1234", "Marcel")
            talk.poll.assert_awaited_once_with("abcd1234", 1)
            hermes.answer.assert_awaited_once()
            self.assertEqual(hermes.answer.await_args.args[0], legacy_session)
            self.assertEqual(state.load("abcd1234")[0], 2)
            state.db.close()
            friday = Settings.load({**OPTIONS, **FRIDAY}, persona="FRIDAY")
            state = State(Path(directory) / "delivery-friday.sqlite3", friday.scope)
            self.assertEqual(state.load("abcd1234")[0], 0)
            await Bridge(friday, state, talk, hermes, None).process_batch("abcd1234", "Marcel")
            self.assertNotEqual(hermes.answer.await_args.args[0], legacy_session)
            state.db.close()

    async def test_file_placeholders_never_reach_the_model(self):
        for entry in (
            message(message="{file}"),
            message(message="*{actor} shared a file which is no longer available*"),
            message(message="*{actor} hat eine Datei geteilt, die nicht mehr vorhanden ist*"),
            message(messageType="system", systemMessage="file_shared"),
        ):
            with self.subTest(entry=entry):
                settings = Settings.load(OPTIONS)
                state = State(":memory:", settings.scope)
                talk, hermes = AsyncMock(), AsyncMock()
                talk.peer.return_value = "Marcel"
                talk.poll.return_value = ([entry], 1)
                with self.assertLogs("hermes-talk", level="WARNING") as logs:
                    await Bridge(settings, state, talk, hermes, None).process_batch("abcd1234", "Marcel")
                hermes.answer.assert_not_awaited()
                self.assertIn("Dateizugriff des App-Passworts", talk.post_text.await_args.args[-1])
                self.assertIn("Talk-Sprachfreigabe", logs.output[0])
                state.db.close()

    async def test_piper_failure_falls_back_to_text_and_advances(self):
        settings = Settings.load(OPTIONS)
        talk, hermes, whisper = AsyncMock(), AsyncMock(), AsyncMock()
        talk.peer.return_value = "Marcel"
        talk.poll.return_value = ([message(1, messageType="voice-message"), message(2)], 2)
        hermes.answer.side_effect = ["Erste Antwort", "Zweite Antwort"]
        state = State(":memory:", settings.scope)
        synthesize = AsyncMock(side_effect=PiperError("Piper DNS/TCP"))
        with patch("talk_worker.piper_audio", synthesize), self.assertLogs("hermes-talk", level="WARNING"):
            await Bridge(settings, state, talk, hermes, whisper).process_batch("abcd1234", "Marcel")
        self.assertEqual(state.load("abcd1234"), (2, None, None, None, None))
        self.assertIn("Erste Antwort", talk.post_text.await_args_list[0].args[-1])
        self.assertEqual(talk.post_text.await_args_list[1].args[-1], "Zweite Antwort")
        talk.post_voice.assert_not_awaited()
        state.db.close()

    async def test_restart_and_duplicate_cursor(self):
        settings = Settings.load(OPTIONS)
        talk = AsyncMock()
        talk.peer.return_value = "Marcel"
        talk.poll.return_value = ([message(), message(), message(2, actorId="hermes")], 3)
        hermes = AsyncMock()
        hermes.answer.return_value = "Antwort"
        talk.post_text.side_effect = [ServiceError("temporary failure"), None]
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "test.sqlite"
            state = State(db, settings.scope)
            bridge = Bridge(settings, state, talk, hermes, AsyncMock())
            with self.assertRaises(ServiceError):
                await bridge.process_batch("abcd1234", "Marcel")
            state.db.close()
            resumed = State(db, settings.scope)
            bridge = Bridge(settings, resumed, talk, hermes, AsyncMock())
            await bridge.process_batch("abcd1234", "Marcel")
            await bridge.process_batch("abcd1234", "Marcel")
            self.assertEqual(resumed.load("abcd1234"), (3, None, None, None, None))
            hermes.answer.assert_awaited_once()
            self.assertEqual(talk.post_text.await_args_list[0], talk.post_text.await_args_list[1])
            resumed.db.close()

    async def test_dropped_message_does_not_reuse_queued_answer(self):
        settings = Settings.load(OPTIONS)
        talk, hermes = AsyncMock(), AsyncMock()
        talk.peer.return_value = "Marcel"
        talk.poll.return_value = ([message(2)], 2)
        hermes.answer.return_value = "Second answer"
        state = State(":memory:", settings.scope)
        state.load("abcd1234")
        state.draft("abcd1234", 1, "First answer", False)
        await Bridge(settings, state, talk, hermes, AsyncMock()).process_batch("abcd1234", "Marcel")
        self.assertEqual(talk.post_text.await_args.args[-1], "Second answer")
        state.db.close()

    async def test_same_context_for_voice_and_text(self):
        settings = Settings.load(OPTIONS)
        talk, hermes, whisper = AsyncMock(), AsyncMock(), AsyncMock()
        talk.peer.return_value = "Marcel"
        talk.poll.return_value = ([message(), message(2, messageType="voice-message")], 2)
        hermes.answer.return_value = "Hallo"
        whisper.transcribe.return_value = "Wie ist das Wetter?"
        state = State(":memory:", settings.scope)
        with patch("talk_worker.piper_audio", new=AsyncMock(return_value=b"mp3")) as piper:
            await Bridge(settings, state, talk, hermes, whisper).process_batch("abcd1234", "Marcel")
        piper.assert_awaited_once_with(settings.piper, "Hallo", settings.voice)
        first, second = hermes.answer.await_args_list
        self.assertEqual(first.args[0], second.args[0])
        self.assertNotEqual(first.args[1], second.args[1])
        self.assertEqual(second.args[2:], ("Wie ist das Wetter?", True))
        talk.post_voice.assert_awaited_once()
        state.db.close()


class WyomingTests(unittest.IsolatedAsyncioTestCase):
    async def test_describe_checks_voice_and_synthesize_sends_exact_name(self):
        from wyoming.audio import AudioChunk, AudioStart, AudioStop
        from wyoming.event import async_read_event, async_write_event
        from wyoming.info import Describe, Info, Attribution, TtsProgram, TtsVoice
        from wyoming.tts import Synthesize

        requests = []
        statuses = []
        settings = [Settings.load({**OPTIONS, **FRIDAY}, persona=persona) for persona in ("JARVIS", "FRIDAY")]
        common = {"attribution": Attribution("Test", ""), "installed": True, "description": None, "version": None}
        voices = [TtsVoice(s.voice, languages=["de-DE"], **common) for s in settings]
        voices.append(TtsVoice("english", languages=["en-US"], **common))

        async def handle(reader, writer):
            try:
                statuses.append(Describe.is_type((await async_read_event(reader)).type))
                await async_write_event(Info(tts=[TtsProgram("piper", voices=voices, **common)]).event(), writer)
                event = await async_read_event(reader)
                if event is not None:
                    requests.append(Synthesize.from_event(event).voice.name)
                    for response in (AudioStart(22050, 2, 1), AudioChunk(22050, 2, 1, b"\x00\x01"), AudioStop()):
                        await async_write_event(response.event(), writer)
            finally:
                writer.close()

        async with await asyncio.start_server(handle, "127.0.0.1", 0) as server:
            endpoint = server.sockets[0].getsockname()
            for setting in settings:
                self.assertEqual(await piper_pcm(endpoint, "Antwort", setting.voice), (22050, b"\x00\x01"))
            for name, error in (("absent", "nicht an"), ("english", "nicht als Deutsch")):
                with self.assertRaisesRegex(PiperError, f"Stimmwahl.*{name}.*{error}"):
                    await piper_pcm(endpoint, "Antwort", name)
        self.assertEqual(statuses, [True] * 4)
        self.assertEqual(requests, [s.voice for s in settings])


class TalkHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def test_gateway_instructions_for_english_input(self):
        async def complete(request):
            self.assertEqual(request.headers["Authorization"], "Bearer example-hermes-key")
            calls.append((await request.json())["messages"])
            return web.json_response({"choices": [{"message": {"content": "Guten Morgen!"}}]},
                                     headers={"X-Hermes-Session-Id": request.headers["X-Hermes-Session-Id"]})

        calls = []
        app = web.Application()
        app.router.add_post("/v1/chat/completions", complete)
        async with TestServer(app) as server, aiohttp.ClientSession() as http:
            with patch("talk_worker.HERMES_URL", str(server.make_url("/")).rstrip("/")):
                for persona in ("JARVIS", "FRIDAY"):
                    settings = Settings.load({**OPTIONS, **FRIDAY}, persona=persona)
                    for voice in (False, True):
                        result = await Hermes(http, settings).answer("session", "turn", "Good morning!", voice)
                        self.assertEqual(result, "Guten Morgen!")
                        instructions, user = calls.pop()
                        self.assertIn(persona, instructions["content"])
                        self.assertIn("immer in natürlichem Deutsch", instructions["content"])
                        self.assertEqual("vorlesbaren" in instructions["content"], voice)
                        self.assertEqual(user, {"role": "user", "content": "Good morning!"})

    async def test_auth_and_ambiguous_share_recovery(self):
        events = []
        uploads = []

        async def talk_api(request):
            if request.headers.get("Authorization") != AUTHORIZATION:
                return web.Response(status=401, text="private server error")
            self.assertEqual(request.headers.get("OCS-APIRequest"), "true")
            if request.path.endswith("/cloud/user"):
                return ocs({"id": "hermes"})
            if request.path.endswith("/cloud/capabilities"):
                return ocs({"capabilities": {"spreed": {"features": [
                    "chat-v2", "chat-reference-id", "voice-message-sharing",
                ]}}})
            if request.path.endswith("/v4/room"):
                return ocs([{"token": "abcd1234", "type": 1}, {"token": "bbbb", "type": 2},
                            {"token": "cccc", "type": 1}, {"token": "dddd", "type": 1, "remoteServer": "x"}])
            if request.path.endswith("/participants"):
                return ocs([{"actorType": "users", "actorId": actor} for actor in ("Marcel", "hermes")])
            if request.path.endswith("/chat/abcd1234"):
                return ocs(events) if events else web.Response(status=304)
            if request.path.endswith("/shares"):
                form = await request.post()
                self.assertEqual(form["shareType"], "10")
                self.assertEqual(form["shareWith"], "abcd1234")
                self.assertEqual(json.loads(form["talkMetaData"]), {"messageType": "voice-message"})
                events.append(message(2, actorId="hermes", referenceId=form["referenceId"]))
                return web.Response(status=504)
            return web.Response(status=404)

        async def dav(request):
            self.assertEqual(request.headers["Authorization"], AUTHORIZATION)
            if request.method == "GET":
                return web.Response(body=b"fake audio")
            if request.method == "PUT":
                uploads.append(await request.read())
            return web.Response(status=201)

        app = web.Application()
        app.router.add_route("*", "/ocs/{tail:.*}", talk_api)
        app.router.add_route("*", "/remote.php/dav/{tail:.*}", dav)
        async with TestServer(app) as server, aiohttp.ClientSession() as http:
            options = {**OPTIONS, "talk_url": str(server.make_url("/"))}
            denied = TalkClient(http, Settings.load({**options, "talk_app_password": "wrong"}, allow_http=True))
            with self.assertRaisesRegex(ServiceError, "Talk-Anmeldung") as raised:
                await denied.check_account()
            self.assertNotIn("private server error", str(raised.exception))
            client = TalkClient(http, Settings.load(options, allow_http=True))
            await client.check_account()
            self.assertEqual(await client.rooms(), ["abcd1234"])
            self.assertEqual(await client.peer("abcd1234"), "Marcel")
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "voice"
                await client.download_voice({"messageParameters": {"file": VOICE_FILE}}, path)
                self.assertEqual(path.read_bytes(), b"fake audio")
            with self.assertRaisesRegex(ServiceError, "504"):
                await client.post_voice("abcd1234", 1, "ref", b"audio")
            await client.post_voice("abcd1234", 1, "ref", b"audio")
            self.assertEqual(uploads, [b"audio"])
            self.assertEqual(len(events), 1)
