"""Voice agent — OpenAI Realtime + Whisper + TTS."""

from __future__ import annotations
import asyncio
import logging
import os

log = logging.getLogger("largestack.voice")


class VoiceAgent:
    """Voice agent using OpenAI APIs. Async-safe file I/O."""

    def __init__(self, model: str = "openai/gpt-4o-realtime-preview", voice: str = "alloy"):
        self.model = model
        self.voice = voice
        self._available = False
        try:
            import openai

            self._openai = openai
            self._available = True
        except ImportError:
            pass

    @property
    def api_key(self) -> str | None:
        return os.environ.get("LARGESTACK_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")

    @property
    def available(self) -> bool:
        return self._available and bool(self.api_key)

    async def transcribe(self, audio_path: str) -> str:
        if not self.available:
            return "OpenAI not configured"
        try:
            client = self._openai.AsyncOpenAI(api_key=self.api_key)
            # Read file off the event loop
            data = await asyncio.to_thread(lambda: open(audio_path, "rb").read())
            import io

            file_obj = io.BytesIO(data)
            file_obj.name = os.path.basename(audio_path)
            resp = await client.audio.transcriptions.create(model="whisper-1", file=file_obj)
            return resp.text
        except Exception as e:
            return f"Transcription error: {e}"

    async def synthesize(self, text: str, output_path: str = "output.mp3") -> str:
        if not self.available:
            return "OpenAI not configured"
        try:
            client = self._openai.AsyncOpenAI(api_key=self.api_key)
            resp = await client.audio.speech.create(model="tts-1", voice=self.voice, input=text)
            await asyncio.to_thread(lambda: open(output_path, "wb").write(resp.content))
            return output_path
        except Exception as e:
            return f"TTS error: {e}"
