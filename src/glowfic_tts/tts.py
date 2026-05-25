"""TTS providers: pure `SynthSpec -> wav bytes` callables.

Adapters only synthesize audio; the orchestrator owns caching and disk writes
(Review fix #4). Both providers emit PCM 24kHz/16-bit mono WAV so clips concat
losslessly regardless of which produced them.
"""

from __future__ import annotations

import io
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Callable

from .models import SynthSpec
from .voices import GEMINI_CHANNELS, GEMINI_SAMPLE_RATE, GEMINI_SAMPLE_WIDTH

Synth = Callable[[SynthSpec], bytes]


def _pcm_to_wav(pcm: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(GEMINI_CHANNELS)
        wav.setsampwidth(GEMINI_SAMPLE_WIDTH)
        wav.setframerate(GEMINI_SAMPLE_RATE)
        wav.writeframes(pcm)
    return buffer.getvalue()


def synth_say(spec: SynthSpec) -> bytes:
    voice = spec.voice.say
    if voice is None:
        raise ValueError(f"Line for {spec.text[:30]!r} has no `say` voice configured.")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "clip.wav"
        subprocess.run(
            [
                "say",
                "-v", voice.voice_name,
                "--file-format=WAVE",
                f"--data-format=LEI16@{GEMINI_SAMPLE_RATE}",
                "-o", str(out),
            ],
            input=spec.text.encode(),
            check=True,
        )
        return out.read_bytes()


def make_gemini_synth(api_key: str | None = None) -> Synth:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key) if api_key else genai.Client()

    def synth(spec: SynthSpec) -> bytes:
        voice = spec.voice.gemini
        if voice is None:
            raise ValueError(f"Line for {spec.text[:30]!r} has no `gemini` voice configured.")
        prompt = f"{voice.style_prompt}\n\n{spec.text}" if voice.style_prompt else spec.text
        response = client.models.generate_content(
            model=spec.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice.voice_name
                        )
                    )
                ),
            ),
        )
        pcm = response.candidates[0].content.parts[0].inline_data.data
        return _pcm_to_wav(pcm)

    return synth
