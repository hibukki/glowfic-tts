"""Gemini TTS voice catalog and defaults.

Facts from the official docs (https://ai.google.dev/gemini-api/docs/speech-generation):
- 30 prebuilt single-speaker voices (below).
- TTS models: gemini-2.5-flash-preview-tts (default here), -pro-preview-tts, gemini-3.1-flash-tts-preview.
- 32k-token context per session; output is PCM 24kHz / 16-bit mono.
- Multi-speaker tops out at 2 voices, so we synthesize one chunk per voice instead.
"""

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

GEMINI_VOICES: list[str] = [
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede",
    "Callirrhoe", "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba",
    "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar",
    "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi",
    "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat",
]
