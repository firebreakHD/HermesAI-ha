"""Join authorized Talk DMs with Chromium and keep call audio local."""

import asyncio
import base64
import json
import logging
import os
import re
import signal
import sys
import time
import uuid
from collections import deque
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp

from talk_audio import Whisper, piper_audio
from talk_client import ServiceError, Settings, TALK, TalkClient
from talk_worker import Hermes

LOG = logging.getLogger("hermes-talk")
JOIN = re.compile(r"^(Join call|Anruf beitreten|An Anruf teilnehmen)$", re.I)
LEAVE = re.compile(r"^(Leave call|Anruf verlassen)$", re.I)
DISABLE_VIDEO = re.compile(r"^(Disable video|Video deaktivieren)( \(V\))?$", re.I)
ENABLE_MIC = re.compile(r"^(Unmute audio|Mikrofon einschalten)( \(M\))?$", re.I)
AUDIO_SCRIPT = Path(__file__).with_name("call_audio.js")
FRAME_BYTES = 640  # 20 ms at 16 kHz, signed 16-bit PCM.
POLL_SECONDS = 2


def remote_session(participants, peer, own_user, *, joined=False):
    """Require one allowed caller and no unexpected attendee or session."""
    remote = []
    own_count = 0
    for attendee in participants:
        session = attendee.get("sessionId")
        if attendee.get("actorType") != "users" or not isinstance(session, str) or not session or session == "0":
            return None
        if attendee.get("actorId") == peer:
            remote.append(session)
        elif attendee.get("actorId") == own_user and joined:
            own_count += 1
        else:
            return None
    return remote[0] if len(remote) == 1 and own_count <= 1 else None


class VoiceActivity:
    def __init__(self, is_speech):
        self.is_speech = is_speech
        self.pending = bytearray()
        self.lead = deque(maxlen=10)
        self.utterance = None
        self.voiced = 0
        self.trailing = 0

    def feed(self, pcm):
        self.pending.extend(pcm)
        while len(self.pending) >= FRAME_BYTES:
            frame = bytes(self.pending[:FRAME_BYTES])
            del self.pending[:FRAME_BYTES]
            speech = self.is_speech(frame)
            if self.utterance is None:
                self.lead.append(frame)
                self.voiced = self.voiced + 1 if speech else 0
                if self.voiced == 3:
                    self.utterance = list(self.lead)
                    self.lead.clear()
                    yield "start", None
                continue
            self.utterance.append(frame)
            self.voiced += int(speech)
            self.trailing = 0 if speech else self.trailing + 1
            if self.trailing >= 30 or len(self.utterance) >= 900:
                if self.voiced >= 8:
                    yield "end", b"".join(self.utterance)
                self.utterance = None
                self.voiced = self.trailing = 0


class Dialogue:
    def __init__(self, page, hermes, whisper, settings):
        self.page = page
        self.hermes = hermes
        self.whisper = whisper
        self.settings = settings
        self.session = "talk-call-" + uuid.uuid4().hex
        self.revision = 0
        self.turns = set()
        self.lock = asyncio.Lock()

    async def event(self, kind, pcm):
        if kind == "start":
            self.revision += 1
            await self.page.evaluate("window.hermesMedia.stop()")
        elif kind == "end":
            task = asyncio.create_task(self.answer(self.revision, pcm))
            self.turns.add(task)
            task.add_done_callback(self.turns.discard)

    async def answer(self, revision, pcm):
        async with self.lock:
            try:
                if revision != self.revision:
                    return
                prompt = await self.whisper.transcribe_pcm(pcm)
                if not prompt or revision != self.revision:
                    return
                reply = await self.hermes.answer(self.session, uuid.uuid4().hex, prompt, True)
                if revision != self.revision:
                    return
                audio = await piper_audio(self.settings.piper, reply, self.settings.voice)
                if revision == self.revision:
                    await self.page.evaluate("audio => window.hermesMedia.play(audio)", base64.b64encode(audio).decode("ascii"))
            except ServiceError as error:
                LOG.warning("%s", error)
            except Exception:
                LOG.warning("Talk-Anruf: Audioausgabe konnte nicht in den Call übertragen werden.")

    async def close(self):
        for task in self.turns:
            task.cancel()
        await asyncio.gather(*self.turns, return_exceptions=True)


class CallWorker:
    def __init__(self, settings, talk, hermes, whisper):
        self.settings = settings
        self.talk = talk
        self.hermes = hermes
        self.whisper = whisper

    async def current(self, room, peer, *, joined=False):
        rooms = await self.talk.direct_messages()
        data = rooms.get(room, {})
        if data.get("hasCall") is not True or await self.talk.peer(room) != peer:
            return None
        session = remote_session(await self.talk.call_participants(room), peer, self.settings.user, joined=joined)
        return (data.get("callStartTime") or 0, session) if session else None

    async def run(self):
        await self.talk.check_account()
        LOG.info("Call-Worker bereit. Warte auf Anrufe aus erlaubten privaten DMs.")
        attempted = {}
        while True:
            try:
                rooms = await self.talk.direct_messages()
                for room in set(attempted) - set(rooms):
                    del attempted[room]
                for room, data in rooms.items():
                    if data.get("hasCall") is not True:
                        attempted.pop(room, None)
                        continue
                    peer = await self.talk.peer(room)
                    if not peer:
                        continue
                    call = await self.current(room, peer)
                    if call and call != attempted.get(room):
                        attempted[room] = call
                        await self.join(room, peer, call)
                        break
            except ServiceError as error:
                LOG.warning("%s", error)
            await asyncio.sleep(POLL_SECONDS)

    async def join(self, room, peer, call):
        from playwright.async_api import Error, TimeoutError as PlaywrightTimeout, async_playwright
        import webrtcvad

        base = self.settings.url
        root = urlsplit(base)
        call_path = root.path + f"{TALK}/v4/call/{room}"
        accepted = False

        async def authorize(route):
            nonlocal accepted
            request = route.request
            url = urlsplit(request.url)
            if ((url.scheme, url.netloc) != (root.scheme, root.netloc)
                    or not url.path.startswith(root.path.rstrip("/") + "/")):
                await route.continue_()
                return
            # Talk uses its own cookie and CSRF session. Send the app password
            # only to the configured Nextcloud, with redirects handled anew.
            if request.resource_type not in {"document", "xhr", "fetch"}:
                await route.continue_()
                return
            try:
                joining = request.method == "POST" and url.path.rstrip("/") == call_path
                other_call = request.method == "POST" and re.search(r"/ocs/v2\.php/apps/spreed/api/v\d+/call/", url.path)
                if other_call and (not joining or accepted or await self.current(room, peer) != call):
                    await route.abort()
                    return
                headers = {**request.headers, "authorization": self.talk.authorization}
                response = await route.fetch(headers=headers, max_redirects=0, timeout=45000)
                if joining and response.ok:
                    accepted = True
                try:
                    await route.fulfill(response=response)
                finally:
                    await response.dispose()
            except (Error, ServiceError):
                try:
                    await route.abort()
                except Error:
                    pass

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                executable_path="/usr/bin/chromium",
                args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
                      "--autoplay-policy=no-user-gesture-required", "--disable-dev-shm-usage",
                      "--disable-background-timer-throttling", "--disable-renderer-backgrounding"],
            )
            try:
                # Nextcloud Talk 22's browser check expects Chromium's standard UA.
                version = browser.version.split(".", 1)[0]
                user_agent = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                              f"Chrome/{version}.0.0.0 Safari/537.36")
                context = await browser.new_context(
                    locale="en-US", user_agent=user_agent, service_workers="block",
                )
                await context.grant_permissions(["microphone", "camera"], origin=f"{root.scheme}://{root.netloc}")
                await context.route("**/*", authorize)
                await context.add_init_script(path=AUDIO_SCRIPT)
                page = await context.new_page()
                await page.goto(f"{base}/index.php/call/{room}", wait_until="domcontentloaded", timeout=20000)
                if await self.current(room, peer) != call:
                    return

                first_run = page.locator("#firstrunwizard").get_by_role(
                    "button", name=re.compile(r"^(Close|Schließen)", re.I),
                ).first
                # Nextcloud can mount the welcome dialog after the call button appears.
                await page.add_locator_handler(first_run, lambda button: button.click(timeout=3000))
                await page.get_by_role("button", name=JOIN).first.click(timeout=12000)
                dialog = page.get_by_role("dialog").filter(has=page.get_by_role("button", name=JOIN))
                join_button = dialog.get_by_role("button", name=JOIN).first
                try:
                    await join_button.wait_for(timeout=5000)
                    for label in (DISABLE_VIDEO, ENABLE_MIC):
                        control = dialog.get_by_role("button", name=label).first
                        if await control.is_visible():
                            await control.click(timeout=2000)
                    await join_button.click(timeout=5000)
                except PlaywrightTimeout:
                    if not accepted:
                        raise
                await page.get_by_role("button", name=LEAVE).first.wait_for(timeout=10000)
                if not accepted:
                    raise ServiceError("Talk-Anruf: Beitritt wurde von Talk nicht bestätigt.")
                LOG.info("Talk-Anruf beigetreten. Warte auf WebRTC-Audio.")
                vad = webrtcvad.Vad(2)
                await self.listen(page, room, peer, call, VoiceActivity(lambda pcm: vad.is_speech(pcm, 16000)))
            except (Error, ServiceError):
                LOG.warning("Talk-Anruf: Beitritt oder Medienverbindung beendet. Talk-Webclient, HPB und TURN prüfen.")
            finally:
                if accepted:
                    try:
                        await page.get_by_role("button", name=LEAVE).first.click(timeout=2500)
                        await page.get_by_role("button", name=LEAVE).first.wait_for(state="hidden", timeout=2500)
                    except Error:
                        pass
                await browser.close()

    async def listen(self, page, room, peer, call, detector):
        dialogue = Dialogue(page, self.hermes, self.whisper, self.settings)
        check_at = 0.0
        last_connected = time.monotonic()
        connected = False
        try:
            while True:
                now = time.monotonic()
                if now >= check_at:
                    if await self.current(room, peer, joined=True) != call:
                        return
                    check_at = now + POLL_SECONDS
                audio = await page.evaluate("window.hermesMedia.drain()")
                if audio["connected"]:
                    last_connected = now
                    if not connected:
                        connected = True
                        LOG.info("Talk-Anruf: WebRTC-Verbindung steht.")
                    for chunk in audio["pcm"]:
                        for kind, pcm in detector.feed(base64.b64decode(chunk)):
                            await dialogue.event(kind, pcm)
                elif now - last_connected > 35:
                    raise ServiceError("Talk-Anruf: keine WebRTC-Verbindung.")
                await asyncio.sleep(0.08)
        finally:
            await dialogue.close()


async def main(persona):
    options = json.loads(Path("/data/options.json").read_text())
    settings = Settings.load(options, persona=persona)
    if settings is None or not settings.calls:
        return 0
    if not settings.piper:
        LOG.error("Talk-Anruf: Zum Einschalten einen Wyoming-Piper-Endpunkt eintragen.")
        return 2
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, asyncio.current_task().cancel)
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=45), cookie_jar=aiohttp.DummyCookieJar(),
    ) as http:
        worker = CallWorker(settings, TalkClient(http, settings), Hermes(http, settings),
                            Whisper(Path("/data/hermes/talk/models")))
        delay = 5
        while True:
            try:
                await worker.run()
            except ServiceError as error:
                LOG.warning("%s Erneuter Verbindungsversuch in %d s.", error, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)


if __name__ == "__main__":
    os.umask(0o077)
    persona = "FRIDAY" if sys.argv[1:] == ["FRIDAY"] else "JARVIS"
    logging.basicConfig(level=logging.INFO, format=f"[Nextcloud Talk {persona}] %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    logging.getLogger("faster_whisper").setLevel(logging.WARNING)
    try:
        sys.exit(asyncio.run(main(persona)))
    except asyncio.CancelledError:
        sys.exit(0)
    except ServiceError as error:
        LOG.error("%s", error)
        sys.exit(2)
    except Exception:
        LOG.error("Talk-Anruf: Call-Worker unerwartet beendet.")
        sys.exit(1)
