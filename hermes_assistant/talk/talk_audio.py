"""Bounded local audio decoding and Whisper, with Wyoming Piper for speech output."""

import asyncio
import json
import math
import socket
import subprocess

from talk_client import InvalidVoice, MAX_VOICE_BYTES, ServiceError

MODEL = "Systran/faster-whisper-small"
MODEL_REVISION = "536b0662742c02347bc0e980a01041f333bce120"
MODEL_FILES = ["config.json", "model.bin", "tokenizer.json", "vocabulary.txt", "preprocessor_config.json"]
MAX_SECONDS = 180
PCM_RATE = 16000
INPUT_FORMATS = "mp3,wav,ogg,mov,matroska,flac,aac"
CODECS = {"mp3", "aac", "opus", "vorbis", "pcm_s16le", "pcm_s24le", "flac"}


def decode_voice(path):
    input_options = ["-protocol_whitelist", "file", "-format_whitelist", INPUT_FORMATS]
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", *input_options, "-show_entries",
             "stream=codec_type,codec_name:format=duration", "-of", "json", str(path)],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10,
        )
        info = json.loads(probe.stdout)
        streams = info["streams"]
        duration = float(info["format"]["duration"])
        if (len(streams) != 1 or streams[0]["codec_type"] != "audio"
                or streams[0]["codec_name"] not in CODECS or not math.isfinite(duration)
                or not 0 < duration <= MAX_SECONDS):
            raise ValueError
        result = subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-threads", "1", *input_options,
             "-i", str(path), "-map", "0:a:0", "-t", str(MAX_SECONDS + 1),
             "-ac", "1", "-ar", str(PCM_RATE), "-f", "s16le", "pipe:1"],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20,
        )
        if not 0 < len(result.stdout) <= 2 * PCM_RATE * MAX_SECONDS:
            raise ValueError
        return result.stdout
    except (subprocess.SubprocessError, KeyError, TypeError, ValueError):
        raise InvalidVoice("Unterstützt werden reine Audiodateien bis zu drei Minuten.") from None


class Whisper:
    def __init__(self, cache):
        self.cache = cache
        self.model = None
        self.lock = asyncio.Lock()

    async def transcribe(self, path):
        async with self.lock:
            return await asyncio.to_thread(self.transcribe_local, path)

    async def transcribe_pcm(self, pcm):
        async with self.lock:
            return await asyncio.to_thread(self._transcribe_pcm, pcm)

    def transcribe_local(self, path):
        return self._transcribe_pcm(decode_voice(path))

    def _transcribe_pcm(self, pcm):
        try:
            import numpy as np
            from faster_whisper import WhisperModel
            from huggingface_hub import snapshot_download
            from huggingface_hub.utils import disable_progress_bars

            if self.model is None:
                disable_progress_bars()
                model_path = snapshot_download(repo_id=MODEL, revision=MODEL_REVISION,
                                               cache_dir=str(self.cache), allow_patterns=MODEL_FILES, token=False)
                self.model = WhisperModel(model_path, device="cpu", compute_type="int8",
                                          cpu_threads=2, local_files_only=True)
            samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
            segments, _ = self.model.transcribe(samples, language="de", beam_size=1, vad_filter=True)
            return " ".join(segment.text.strip() for segment in segments).strip()
        except Exception:
            raise ServiceError("Whisper: lokales Modell konnte nicht geladen werden oder Transkription fehlgeschlagen.") from None


class PiperError(ServiceError):
    """A speech output failure that still permits a text reply."""


async def piper_pcm(endpoint, text, voice):
    from wyoming.audio import AudioChunk, AudioStart, AudioStop
    from wyoming.event import async_read_event, async_write_event
    from wyoming.info import Describe, Info
    from wyoming.tts import Synthesize, SynthesizeVoice

    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(*endpoint), timeout=5)
    except socket.gaierror:
        raise PiperError("Piper DNS: Der konfigurierte Wyoming-Hostname ist nicht auflösbar.") from None
    except (OSError, TimeoutError):
        raise PiperError("Piper DNS/TCP: Keine Verbindung zum konfigurierten Wyoming-Port.") from None

    phase = "Describe/Info"
    try:
        async with asyncio.timeout(10):
            await async_write_event(Describe().event(), writer)
            event = await async_read_event(reader)
            if event is None or not Info.is_type(event.type):
                raise ValueError
            voices = [candidate for program in Info.from_event(event).tts for candidate in program.voices]
        matches = [candidate for candidate in voices if candidate.name == voice]
        if not matches:
            raise PiperError(f"Piper Stimmwahl: Der Wyoming-Dienst bietet '{voice}' nicht an. "
                             "Stimme im Piper-Dienst bereitstellen oder Add-on-Konfiguration anpassen.")
        if not any(language.lower().replace("_", "-").split("-")[0] == "de"
                   for match in matches for language in match.languages):
            raise PiperError(f"Piper Stimmwahl: '{voice}' wird vom Wyoming-Dienst nicht als Deutsch angeboten.")

        phase = "Synthesize/Audio"
        async with asyncio.timeout(90):
            await async_write_event(Synthesize(text=text[:6000], voice=SynthesizeVoice(name=voice)).event(),
                                    writer)
            start = None
            pcm = bytearray()
            while event := await async_read_event(reader):
                if AudioStart.is_type(event.type):
                    if start is not None:
                        raise ValueError
                    start = AudioStart.from_event(event)
                    if (start.rate not in {16000, 22050, 24000, 44100, 48000}
                            or start.width != 2 or start.channels != 1):
                        raise ValueError
                elif AudioChunk.is_type(event.type):
                    chunk = AudioChunk.from_event(event)
                    if (start is None or (chunk.rate, chunk.width, chunk.channels)
                            != (start.rate, start.width, start.channels)):
                        raise ValueError
                    pcm.extend(chunk.audio)
                    if len(pcm) > min(MAX_VOICE_BYTES, start.rate * 2 * MAX_SECONDS):
                        raise ValueError
                elif AudioStop.is_type(event.type) and start is not None and pcm and len(pcm) % 2 == 0:
                    return start.rate, pcm
                else:
                    raise ValueError
            raise ValueError
    except (OSError, TimeoutError, EOFError, ValueError, TypeError, KeyError, AttributeError):
        raise PiperError(f"Piper Wyoming-Protokoll ({phase}): Keine gültige Dienstantwort. "
                         "Piper-Dienst und Voice-Installation prüfen.") from None
    finally:
        writer.close()


async def piper_audio(endpoint, text, voice):
    rate, pcm = await piper_pcm(endpoint, text, voice)
    try:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-nostdin", "-v", "error", "-f", "s16le", "-ar", str(rate),
            "-ac", "1", "-i", "pipe:0", "-c:a", "libmp3lame", "-b:a", "64k", "-f", "mp3", "pipe:1",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            output, _ = await asyncio.wait_for(process.communicate(pcm), timeout=20)
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
        if process.returncode != 0 or not 0 < len(output) <= MAX_VOICE_BYTES:
            raise ValueError
        return output
    except (OSError, TimeoutError, ValueError):
        raise PiperError("Piper Audio-Konvertierung: FFmpeg konnte kein MP3 aus dem Wyoming-Audio erzeugen.") from None
