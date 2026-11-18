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

from talk_audio import decode_voice
from talk_client import InvalidVoice, ServiceError, Settings, TalkClient, voice_path
from talk_worker import Bridge, State, message_kind

AUTHORIZATION = "Basic aGVybWVzOmV4YW1wbGUtYXBwLXBhc3N3b3Jk"
OPTIONS = {
    "talk_enabled": True,
    "talk_url": "https://nextcloud.example.invalid",
    "talk_username": "hermes",
    "talk_app_password": "example-app-password",
    "talk_allowed_users": ["alice"],
    "talk_allowed_rooms": ["abcd1234"],
    "api_server_key": "example-hermes-key",
    "talk_piper_endpoint": "tcp://local-piper:10200",
}
VOICE_FILE = {"type": "file", "path": "Talk/note.mp3", "permissions": "1", "size": "1500"}


def message(message_id=1, **kwargs):
    return {"token": "abcd1234", "actorType": "users", "actorId": "alice", "messageType": "comment",
            "systemMessage": "", "message": "Guten Morgen", "timestamp": 2_000_000_000,
            "id": message_id, **kwargs}


def ocs(data):
    return web.json_response({"ocs": {"meta": {"statuscode": 200}, "data": data}})


class SettingsTests(unittest.TestCase):
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
        self.assertEqual(message_kind(message(), "abcd1234", "alice", 0), "text")
        voice = message(messageType="voice-message", systemMessage="file_shared")
        self.assertEqual(message_kind(voice, "abcd1234", "alice", 0), "voice")
        for changed in (
            {"actorId": "hermes"}, {"actorId": "bob"}, {"actorType": "federated_users"},
            {"token": "anotherroom"}, {"timestamp": 0}, {"systemMessage": "file_shared"},
            {"messageType": "system"}, {"messageType": "command"},
        ):
            self.assertIsNone(message_kind(message(**changed), "abcd1234", "alice", 1))

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
    async def test_restart_and_duplicate_cursor(self):
        settings = Settings.load(OPTIONS)
        talk = AsyncMock()
        talk.peer.return_value = "alice"
        talk.poll.return_value = ([message(), message(), message(2, actorId="hermes")], 3)
        hermes = AsyncMock()
        hermes.answer.return_value = "Antwort"
        talk.post_text.side_effect = [ServiceError("temporary failure"), None]
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "test.sqlite"
            state = State(db, settings.scope)
            bridge = Bridge(settings, state, talk, hermes, AsyncMock())
            with self.assertRaises(ServiceError):
                await bridge.process_batch("abcd1234", "alice")
            state.db.close()
            resumed = State(db, settings.scope)
            bridge = Bridge(settings, resumed, talk, hermes, AsyncMock())
            await bridge.process_batch("abcd1234", "alice")
            await bridge.process_batch("abcd1234", "alice")
            self.assertEqual(resumed.load("abcd1234"), (3, None, None, None, None))
            hermes.answer.assert_awaited_once()
            self.assertEqual(talk.post_text.await_args_list[0], talk.post_text.await_args_list[1])
            resumed.db.close()

    async def test_dropped_message_does_not_reuse_queued_answer(self):
        settings = Settings.load(OPTIONS)
        talk, hermes = AsyncMock(), AsyncMock()
        talk.peer.return_value = "alice"
        talk.poll.return_value = ([message(2)], 2)
        hermes.answer.return_value = "Second answer"
        state = State(":memory:", settings.scope)
        state.load("abcd1234")
        state.draft("abcd1234", 1, "First answer", False)
        await Bridge(settings, state, talk, hermes, AsyncMock()).process_batch("abcd1234", "alice")
        self.assertEqual(talk.post_text.await_args.args[-1], "Second answer")
        state.db.close()

    async def test_same_context_for_voice_and_text(self):
        settings = Settings.load(OPTIONS)
        talk, hermes, whisper = AsyncMock(), AsyncMock(), AsyncMock()
        talk.peer.return_value = "alice"
        talk.poll.return_value = ([message(), message(2, messageType="voice-message")], 2)
        hermes.answer.return_value = "Hallo"
        whisper.transcribe.return_value = "Wie ist das Wetter?"
        state = State(":memory:", settings.scope)
        with patch("talk_worker.piper_audio", new=AsyncMock(return_value=b"mp3")):
            await Bridge(settings, state, talk, hermes, whisper).process_batch("abcd1234", "alice")
        first, second = hermes.answer.await_args_list
        self.assertEqual(first.args[0], second.args[0])
        self.assertNotEqual(first.args[1], second.args[1])
        self.assertEqual(second.args[2:], ("Wie ist das Wetter?", True))
        talk.post_voice.assert_awaited_once()
        state.db.close()


class TalkHTTPTests(unittest.IsolatedAsyncioTestCase):
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
                return ocs([{"actorType": "users", "actorId": actor} for actor in ("alice", "hermes")])
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
            self.assertEqual(await client.peer("abcd1234"), "alice")
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "voice"
                await client.download_voice({"messageParameters": {"file": VOICE_FILE}}, path)
                self.assertEqual(path.read_bytes(), b"fake audio")
            with self.assertRaisesRegex(ServiceError, "504"):
                await client.post_voice("abcd1234", 1, "ref", b"audio")
            await client.post_voice("abcd1234", 1, "ref", b"audio")
            self.assertEqual(uploads, [b"audio"])
            self.assertEqual(len(events), 1)
