"""Shared schema for the glowfic -> audio pipeline.

Every stage imports these types; only the orchestrator reads/writes them to disk.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel


class Coverage(BaseModel):
    """How much of a post an artifact covers.

    Stamped on every artifact so a sliced run can never be mistaken for, or fed
    into, a full run.
    """

    kind: Literal["full", "limit"]
    limit: int | None = None  # number of replies, set when kind == "limit"

    def slug(self) -> str:
        return "full" if self.kind == "full" else f"limit_{self.limit}"

    @classmethod
    def of(cls, limit: int | None) -> "Coverage":
        # `limit is None` (not falsy) so --limit 0 stays a limited run and never
        # writes into the `full` path.
        return cls(kind="full") if limit is None else cls(kind="limit", limit=limit)


# --- rich text: preserves emphasis without forcing TTS to use it ---


class TextRun(BaseModel):
    text: str
    emphasis: bool = False  # <em>/<i>
    strong: bool = False  # <strong>/<b>


class RichText(BaseModel):
    runs: list[TextRun]

    def plain(self) -> str:
        """Flatten to plain text — what the first TTS pass speaks."""
        return "".join(run.text for run in self.runs)


# --- who is speaking / which voice key ---


class Speaker(BaseModel):
    character_id: int | None
    character_name: str | None
    screenname: str | None
    username: str  # the author; always present

    @property
    def voice_key(self) -> str:
        """Stable, human-readable key into the voice map.

        Prefers the character's display name (nice to edit in voices.toml);
        falls back to the author for narrator/author-only segments. Known
        simplification: two distinct characters sharing a name within one post
        would collide — `character_id` is kept so we can detect that later.
        """
        name = self.character_name or self.screenname
        return name if name else f"@{self.username}"


# --- canonical story (step 2) ---


class Segment(BaseModel):
    seq: int  # 0 = opening post, 1.. = replies in API order
    reply_id: int | None  # None for the opening post
    speaker: Speaker
    icon_keyword: str | None
    content_html: str  # raw, kept for traceability


class Story(BaseModel):
    coverage: Coverage
    post_id: int
    subject: str
    authors: list[Speaker]
    segments: list[Segment]


# --- parsed + chunked script (step 3) ---


class Chunk(BaseModel):
    seq: int
    chunk_index: int
    voice_key: str  # the speaker travels with the text
    rich: RichText


class Script(BaseModel):
    coverage: Coverage
    post_id: int
    subject: str
    chunks: list[Chunk]
    speakers: dict[str, Speaker]  # voice_key -> Speaker (drives voices.toml)


# --- multi-provider voice config (step 4) ---


class GeminiVoice(BaseModel):
    voice_name: str  # e.g. "Kore", "Puck" — verify list against official docs
    style_prompt: str | None = None  # room for emphasis/tone later


class ElevenLabsVoice(BaseModel):
    voice_id: str


class MacSayVoice(BaseModel):
    voice_name: str  # a macOS `say -v` voice, e.g. "Samantha" — free/offline, for iterating


class Voice(BaseModel):
    gemini: GeminiVoice | None = None
    elevenlabs: ElevenLabsVoice | None = None
    say: MacSayVoice | None = None
    # Optional epithet spoken in the self-introduction, e.g. "lantalótë".
    # Glowfic has no such field, so it's yours to fill in voices.toml.
    title: str | None = None


class VoiceMap(BaseModel):
    voices: dict[str, Voice]  # voice_key -> Voice (voices.toml)


# --- bound lines (step 4b) ---


class Line(BaseModel):
    seq: int
    chunk_index: int
    voice_key: str
    voice: Voice  # resolved from the VoiceMap
    text: str  # rich.plain() for now


class Lines(BaseModel):
    coverage: Coverage
    post_id: int
    lines: list[Line]


# --- audio (step 5) ---


class SynthSpec(BaseModel):
    """The full fingerprint that determines a clip's audio.

    The cache key hashes *all* of these, so changing a voice, format, or any
    TTS param invalidates stale audio instead of silently reusing it.
    """

    provider: str
    model: str
    voice: Voice
    output_format: str
    text: str
    params: dict[str, str | float | int] = {}

    def key(self) -> str:
        payload = self.model_dump_json()  # field order is the declaration order
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


class AudioClip(BaseModel):
    seq: int
    chunk_index: int
    synthesis_key: str
    spec: SynthSpec  # resolved config stored, not just the provider name
    path: str


class AudioManifest(BaseModel):
    coverage: Coverage
    post_id: int
    clips: list[AudioClip]
