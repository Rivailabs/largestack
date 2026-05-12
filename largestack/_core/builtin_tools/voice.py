"""Voice pipeline — STT → Agent → TTS (<400ms target)."""
from largestack._core.tools import tool

@tool(timeout=30)
async def speech_to_text(audio_path: str) -> str:
    """Transcribe audio file to text using Whisper."""
    try:
        import httpx, os
        key = os.environ.get("LARGESTACK_OPENAI_API_KEY", "")
        if not key: return "No OpenAI API key for Whisper"
        async with httpx.AsyncClient() as c:
            with open(audio_path, "rb") as f:
                r = await c.post("https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {key}"},
                    files={"file": f}, data={"model": "whisper-1"})
            return r.json().get("text", "Transcription failed")
    except Exception as e:
        return f"STT error: {e}"

@tool(timeout=30)
async def text_to_speech(text: str, voice: str = "alloy") -> str:
    """Convert text to speech using OpenAI TTS."""
    try:
        import httpx, os
        key = os.environ.get("LARGESTACK_OPENAI_API_KEY", "")
        if not key: return "No API key"
        async with httpx.AsyncClient() as c:
            r = await c.post("https://api.openai.com/v1/audio/speech",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": "tts-1", "input": text[:4096], "voice": voice})
            import tempfile

            with tempfile.NamedTemporaryFile(
                prefix="largestack_tts_output_",
                suffix=".mp3",
                delete=False,
            ) as tmp:
                tmp.write(r.content)
                path = tmp.name

            return f"Audio saved to {path}"
    except Exception as e:
        return f"TTS error: {e}"
