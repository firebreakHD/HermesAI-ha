import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "talk"))

from call_worker import CallWorker, Dialogue, FRAME_BYTES, VoiceActivity, remote_session


def attendee(user, session=None, kind="users"):
    return {"actorType": kind, "actorId": user, "sessionId": session or (user + "-session")}


class CallAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    def test_only_one_authorized_remote_session(self):
        peer = attendee("alice")
        own = attendee("hermes")
        for participants in ([own], [peer, own], [peer, attendee("other")],
                             [peer, attendee("alice", "second-tab")], [attendee("alice", kind="guests")]):
            self.assertIsNone(remote_session(participants, "alice", "hermes"))
        self.assertEqual(remote_session([peer], "alice", "hermes"), "alice-session")
        self.assertEqual(remote_session([peer, own], "alice", "hermes", joined=True), "alice-session")
        self.assertIsNone(remote_session([own], "alice", "hermes", joined=True))
        self.assertIsNone(remote_session([peer, own, attendee("hermes", "second")],
                                         "alice", "hermes", joined=True))

    async def test_has_call_requires_authorized_peer_and_active_session(self):
        talk = AsyncMock()
        talk.direct_messages.return_value = {"abcd": {"hasCall": True, "callStartTime": 42}}
        talk.peer.return_value = None
        worker = CallWorker(SimpleNamespace(user="hermes"), talk, None, None)
        self.assertIsNone(await worker.current("abcd", "alice"))
        talk.call_participants.assert_not_awaited()
        talk.peer.return_value = "alice"
        talk.call_participants.return_value = [attendee("bob")]
        self.assertIsNone(await worker.current("abcd", "alice"))
        talk.call_participants.return_value = [attendee("alice")]
        self.assertEqual(await worker.current("abcd", "alice"), (42, "alice-session"))
        talk.direct_messages.return_value = {"abcd": {"hasCall": False}}
        self.assertIsNone(await worker.current("abcd", "alice"))


class CallAudioTests(unittest.IsolatedAsyncioTestCase):
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
        dialogue = Dialogue(page, hermes, whisper, ("piper", 10200))
        await dialogue.event("start", None)
        await dialogue.event("end", b"pcm")
        await asyncio.wait_for(listen.wait(), 1)
        await dialogue.event("start", None)
        signal.set()
        await asyncio.gather(*dialogue.turns)
        self.assertEqual([call.args for call in page.evaluate.await_args_list],
                         [("window.hermesMedia.stop()",), ("window.hermesMedia.stop()",)])
        self.assertTrue(hermes.answer.await_args.args[0].startswith("talk-call-"))
