"""Gemini TTS voice catalog and defaults.

Facts from the official docs (https://ai.google.dev/gemini-api/docs/speech-generation):
- 30 prebuilt single-speaker voices (below).
- TTS models: gemini-2.5-flash-preview-tts (default here), -pro-preview-tts, gemini-3.1-flash-tts-preview.
- 32k-token context per session; output is PCM 24kHz / 16-bit mono.
- Multi-speaker tops out at 2 voices, so we synthesize one chunk per voice instead.
"""

import re
import subprocess

GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts"
GEMINI_OUTPUT_FORMAT = "wav"  # we wrap the raw PCM as WAV
GEMINI_SAMPLE_RATE = 24000
GEMINI_SAMPLE_WIDTH = 2  # bytes, i.e. 16-bit
GEMINI_CHANNELS = 1

# Natural-sounding macOS `say` voices (novelty ones like Bubbles/Zarvox excluded),
# for free/offline iteration. Verify availability with: say -v '?'
MAC_SAY_VOICES: list[str] = [
    "Samantha", "Daniel", "Karen", "Moira", "Rishi", "Tessa",
    "Fred", "Ralph", "Albert", "Kathy", "Tara", "Junior",
]

# Legacy MacinTalk voices — robotic/unclear, never auto-assigned. Re-running
# `voices` reassigns any character currently stuck on one of these.
MAC_SAY_BLACKLIST: set[str] = {"Fred", "Ralph", "Albert", "Junior", "Kathy"}

# A `say -v '?'` line: "Name (Premium)      en_US    # sample". The name may
# contain spaces/parens, then the BCP-47-ish language code, then a comment.
_SAY_VOICE_LINE = re.compile(r"^(.+?)\s+([a-z]{2}_[A-Z]{2})\s+#")

SAY_INSTALL_HELP = (
    "Install Enhanced/Premium English voices (one-time):\n"
    "  System Settings -> Accessibility -> Spoken Content -> System Voice\n"
    "  -> Manage Voices...  then expand English and download a few voices\n"
    "  marked (Enhanced) or (Premium) — e.g. Ava, Tom, Allison, Evan, Zoe.\n"
    "Verify with:  say -v '?' | grep -E 'Premium|Enhanced'\n"
    "Or skip macOS voices entirely with the cloud option:  --provider gemini"
)


def installed_say_voices() -> list[str]:
    out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, check=True).stdout
    return [m.group(1).strip() for line in out.splitlines() if (m := _SAY_VOICE_LINE.match(line))]


def installed_quality_say_voices() -> list[str]:
    """Installed English voices that are Enhanced or Premium (the clear ones)."""
    out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, check=True).stdout
    voices = []
    for line in out.splitlines():
        m = _SAY_VOICE_LINE.match(line)
        if m and m.group(2).startswith("en") and ("premium" in line.lower() or "enhanced" in line.lower()):
            voices.append(m.group(1).strip())
    return voices

GEMINI_VOICES: list[str] = [
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede",
    "Callirrhoe", "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba",
    "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar",
    "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi",
    "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat",
]
