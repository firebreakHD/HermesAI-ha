import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "talk"))

from call_worker import CallWorker, Dialogue, FRAME_BYTES, VoiceActivity, remote_session
from test_talk import OPTIONS, FRIDAY
from talk_client import Settings


def attendee(user, session=None, kind="users"):
    return {"actorType": kind, "actorId": user, "sessionId": session or (user + "-session")}


class CallAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    def test_only_one_authorized_remote_session(self):
        peer = attendee("Marcel")
        own = attendee("hermes")
        for participants in ([own], [peer, own], [peer, attendee("other")],
                             [peer, attendee("Marcel", "second-tab")], [attendee("Marcel", kind="guests")]):
            self.assertIsNone(remote_session(participants, "Marcel", "hermes"))
        self.assertEqual(remote_session([peer], "Marcel", "hermes"), "Marcel-session")
        self.assertEqual(remote_session([peer, own], "Marcel", "hermes", joined=True), "Marcel-session")
        self.assertIsNone(remote_session([own], "Marcel", "hermes", joined=True))
        self.assertIsNone(remote_session([peer, own, attendee("hermes", "second")],
                                         "Marcel", "hermes", joined=True))

    async def test_has_call_requires_authorized_peer_and_active_session(self):
        talk = AsyncMock()
        talk.direct_messages.return_value = {"abcd": {"hasCall": True, "callStartTime": 42}}
        talk.peer.return_value = None
        worker = CallWorker(SimpleNamespace(user="hermes"), talk, None, None)
        self.assertIsNone(await worker.current("abcd", "Marcel"))
        talk.call_participants.assert_not_awaited()
        talk.peer.return_value = "Marcel"
        talk.call_participants.return_value = [attendee("bob")]
        self.assertIsNone(await worker.current("abcd", "Marcel"))
        talk.call_participants.return_value = [attendee("Marcel")]
        self.assertEqual(await worker.current("abcd", "Marcel"), (42, "Marcel-session"))
        talk.direct_messages.return_value = {"abcd": {"hasCall": False}}
        self.assertIsNone(await worker.current("abcd", "Marcel"))


class CallAudioTests(unittest.IsolatedAsyncioTestCase):
    async def test_call_audio_uses_each_contacts_voice_and_a_fresh_session(self):
        sessions = set()
        for persona in ("JARVIS", "FRIDAY", "JARVIS"):
            settings = Settings.load({**OPTIONS, **FRIDAY}, persona=persona)
            page, hermes, whisper = AsyncMock(), AsyncMock(), AsyncMock()
            whisper.transcribe_pcm.return_value = "Good morning!"
            hermes.answer.return_value = "Guten Morgen!"
            call = Dialogue(page, hermes, whisper, settings)
            with patch("call_worker.piper_audio", new=AsyncMock(return_value=b"mp3")) as piper:
                await call.answer(0, b"pcm")
            piper.assert_awaited_once_with(settings.piper, "Guten Morgen!", settings.voice)
            self.assertEqual(hermes.answer.await_args.args[2:], ("Good morning!", True))
            self.assertNotIn(call.session, sessions)
            sessions.add(call.session)
            page.evaluate.assert_awaited_once_with("audio => window.hermesMedia.play(audio)", "bXAz")

    def test_vad_threshold_and_end_of_speech(self):
        voice = b"v" * FRAME_BYTES
        silence = bytes(FRAME_BYTES)
        detector = VoiceActivity(lambda frame: frame == voice)
        self.assertEqual(list(detector.feed(silence * 10 + voice[:300])), [])
        self.assertEqual(list(detector.feed(voice[300:] + voice * 2)), [("start", None)])
        self.assertEqual(list(detector.feed(voice * 5 + silence * 29)), [])
        [(kind, result)] = list(detector.feed(silence))
        self.assertEqual(kind, "end")
        self.assertEqual(result, silence * 7 + voice * 8 + silence * 30)

    async def test_barge_in_stops_playback_and_discards_stale_answer(self):
        page = AsyncMock()
        signal = asyncio.Event()
        listen = asyncio.Event()

        async def answer(*args):
            listen.set()
            await signal.wait()
            return "stale"

        hermes = AsyncMock()
        hermes.answer.side_effect = answer
        whisper = AsyncMock()
        whisper.transcribe_pcm.return_value = "first turn"
        dialogue = Dialogue(page, hermes, whisper, Settings.load(OPTIONS))
        await dialogue.event("start", None)
        await dialogue.event("end", b"pcm")
        await asyncio.wait_for(listen.wait(), 1)
        await dialogue.event("start", None)
        signal.set()
        await asyncio.gather(*dialogue.turns)
        self.assertEqual([call.args for call in page.evaluate.await_args_list],
                         [("window.hermesMedia.stop()",), ("window.hermesMedia.stop()",)])
        self.assertTrue(hermes.answer.await_args.args[0].startswith("talk-call-"))
