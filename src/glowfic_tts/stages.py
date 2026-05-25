"""Pure transform stages: object in, object out, no disk or network.

The orchestrator (pipeline.py) loads inputs, calls these, and saves outputs.
"""

from __future__ import annotations

import re

from .api import RawApiPost, RawCharacter, RawPost, RawUser
from .html_text import parse_paragraphs
from .models import Chunk, RichText, Script, Segment, Speaker, Story, TextRun

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
