"""Pure transform stages: object in, object out, no disk or network.

The orchestrator (pipeline.py) loads inputs, calls these, and saves outputs.
"""

from __future__ import annotations

from .api import RawApiPost, RawCharacter, RawPost, RawUser
from .models import Segment, Speaker, Story


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
