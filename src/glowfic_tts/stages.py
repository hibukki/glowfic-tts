"""Pure transform stages: object in, object out, no disk or network.

The orchestrator (pipeline.py) loads inputs, calls these, and saves outputs.
"""

from __future__ import annotations

import re
from collections import Counter

from .api import RawApiPost, RawCharacter, RawPost, RawUser
from .html_text import parse_paragraphs
from .models import (
    Chunk,
    GeminiVoice,
    Line,
    Lines,
    MacSayVoice,
    RichText,
    Script,
    Segment,
    Speaker,
    Story,
    TextRun,
    Voice,
    VoiceMap,
)
from .voices import GEMINI_VOICES, MAC_SAY_BLACKLIST, MAC_SAY_VOICES

# Conservative vs the Gemini TTS input limit; confirm the real cap when wiring tts.
DEFAULT_MAX_CHARS = 3000


def _speaker(character: RawCharacter | None, user: RawUser) -> Speaker:
    return Speaker(
        character_id=character.id if character else None,
        character_name=character.name if character else None,
        screenname=character.screenname if character else None,
        username=user.username,
    )


def assemble(raw: RawPost) -> Story:
    post: RawApiPost = raw.post
    # The opening post always has a character, so its voice_key never falls back
    # to the username; authors[0] is just a placeholder for that unused fallback.
    opening = Segment(
        seq=0,
        reply_id=None,
        speaker=_speaker(post.character, post.authors[0]),
        icon_keyword=post.icon.keyword if post.icon else None,
        content_html=post.content,
    )
    replies = [
        Segment(
            seq=i,
            reply_id=reply.id,
            speaker=_speaker(reply.character, reply.user),
            icon_keyword=reply.icon.keyword if reply.icon else None,
            content_html=reply.content,
        )
        for i, reply in enumerate(raw.replies, start=1)
    ]
    return Story(
        coverage=raw.coverage,
        post_id=post.id,
        subject=post.subject,
        authors=[_speaker(None, u) for u in post.authors],
        segments=[opening, *replies],
    )


_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")


def _runs_len(runs: list[TextRun]) -> int:
    return sum(len(run.text) for run in runs)


def _split_text(text: str, max_chars: int) -> list[str]:
    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_BREAK.split(text):
        if current and len(current) + 1 + len(sentence) > max_chars:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)

    hard_split: list[str] = []
    for piece in pieces:
        while len(piece) > max_chars:
            hard_split.append(piece[:max_chars])
            piece = piece[max_chars:]
        if piece:
            hard_split.append(piece)
    return hard_split


def _split_long_paragraph(runs: list[TextRun], max_chars: int):
    current: list[TextRun] = []
    for run in runs:
        if len(run.text) > max_chars:
            if current:
                yield current
                current = []
            for piece in _split_text(run.text, max_chars):
                yield [TextRun(text=piece, emphasis=run.emphasis, strong=run.strong)]
            continue
        if current and _runs_len(current) + len(run.text) > max_chars:
            yield current
            current = []
        current.append(run)
    if current:
        yield current


def _pack_paragraphs(paragraphs: list[list[TextRun]], max_chars: int):
    separator = TextRun(text="\n\n")
    current: list[TextRun] = []
    for paragraph in paragraphs:
        if _runs_len(paragraph) > max_chars:
            if current:
                yield current
                current = []
            yield from _split_long_paragraph(paragraph, max_chars)
            continue
        added = (len(separator.text) if current else 0) + _runs_len(paragraph)
        if current and _runs_len(current) + added > max_chars:
            yield current
            current = []
        if current:
            current.append(separator)
        current.extend(paragraph)
    if current:
        yield current


def extract(story: Story, max_chars: int = DEFAULT_MAX_CHARS) -> Script:
    chunks: list[Chunk] = []
    speakers: dict[str, Speaker] = {}
    for segment in story.segments:
        voice_key = segment.speaker.voice_key
        speakers.setdefault(voice_key, segment.speaker)
        paragraphs = parse_paragraphs(segment.content_html)
        for chunk_index, runs in enumerate(_pack_paragraphs(paragraphs, max_chars)):
            chunks.append(
                Chunk(
                    seq=segment.seq,
                    chunk_index=chunk_index,
                    voice_key=voice_key,
                    rich=RichText(runs=runs),
                )
            )
    return Script(
        coverage=story.coverage,
        post_id=story.post_id,
        subject=story.subject,
        chunks=chunks,
        speakers=speakers,
    )


def make_voicemap(
    script: Script,
    existing: VoiceMap | None = None,
    say_voices: list[str] = MAC_SAY_VOICES,
    say_blacklist: set[str] = MAC_SAY_BLACKLIST,
) -> VoiceMap:
    """Assign a voice to every speaker, preserving choices the user already made.

    Voices needing assignment go to the least-used option, so distinct speakers
    get distinct voices until the pool runs out (then reuse is balanced). User
    edits are kept, except a blacklisted `say` voice is reassigned to a clear one.
    """
    say_pool = [v for v in say_voices if v not in say_blacklist]
    prior = existing.voices if existing else {}
    keys = sorted(script.speakers)

    kept_gemini: dict[str, GeminiVoice | None] = {}
    kept_say: dict[str, MacSayVoice | None] = {}
    used_gemini: Counter[str] = Counter()
    used_say: Counter[str] = Counter()
    for key in keys:
        old = prior.get(key)
        gemini = old.gemini if (old and old.gemini) else None
        # Keep a say voice only if it's a valid choice from the current pool, so
        # already-good voices survive untouched (no needless audio regen) while
        # stale/standard ones get reassigned.
        say = old.say if (old and old.say and old.say.voice_name in say_pool) else None
        kept_gemini[key], kept_say[key] = gemini, say
        if gemini:
            used_gemini[gemini.voice_name] += 1
        if say:
            used_say[say.voice_name] += 1

    voices: dict[str, Voice] = {}
    for key in keys:
        gemini = kept_gemini[key]
        if gemini is None:
            name = min(GEMINI_VOICES, key=lambda v: used_gemini[v])
            used_gemini[name] += 1
            gemini = GeminiVoice(voice_name=name)
        say = kept_say[key]
        if say is None:
            name = min(say_pool, key=lambda v: used_say[v])
            used_say[name] += 1
            say = MacSayVoice(voice_name=name)
        voices[key] = Voice(gemini=gemini, say=say, title=prior[key].title if key in prior else None)

    # Don't drop characters from other coverages that share this voices.toml.
    for key, voice in prior.items():
        voices.setdefault(key, voice)
    return VoiceMap(voices=voices)


def _introduction(speaker: Speaker, voice: Voice) -> str | None:
    """e.g. "Alexeara Cansellarion. third-of-that-name. lantalótë." — separate
    sentences so the TTS pauses between them. None for character-less narration."""
    if not speaker.character_name:
        return None
    parts = [speaker.character_name]
    if speaker.screenname and speaker.screenname != speaker.character_name:
        parts.append(speaker.screenname)
    if voice.title:
        parts.append(voice.title)
    return ". ".join(parts) + "."


def bind(script: Script, voicemap: VoiceMap, announce_first_appearance: bool = True) -> Lines:
    lines: list[Line] = []
    introduced: set[str] = set()
    for chunk in script.chunks:
        voice = voicemap.voices.get(chunk.voice_key)
        if voice is None:
            raise KeyError(f"No voice mapped for speaker {chunk.voice_key!r}; run `voices` first.")
        text = chunk.rich.plain()
        if announce_first_appearance and chunk.voice_key not in introduced:
            intro = _introduction(script.speakers[chunk.voice_key], voice)
            if intro:
                text = f"{intro}\n\n{text}"
        introduced.add(chunk.voice_key)
        lines.append(
            Line(
                seq=chunk.seq,
                chunk_index=chunk.chunk_index,
                voice_key=chunk.voice_key,
                voice=voice,
                text=text,
            )
        )
    return Lines(coverage=script.coverage, post_id=script.post_id, lines=lines)
