"""Character genders — the source of truth for gender-matched voice casting.

Autocast won't guess: a character missing here makes the build fail with a
worklist. Use the casting preview's art + opening line to decide, then add them.
'N' = narration / settings / no single gender (any voice is fine).
"""

from __future__ import annotations

from .models import Speaker

CHARACTER_GENDERS: dict[str, str] = {
    # post 53182 — paths we seek in vain
    "merrin": "F",
    "vicar esta": "M",
    "laeirthe": "M",
    "asmodeus": "M",
    "aspexia rugatonn": "F",
    "dath ilan": "N",
    "places": "N",
    "unnamed exoplanet": "N",
    "cheliax": "N",
    "various gods": "N",
}


VALID_GENDERS = ("M", "F", "N")


def is_known_gender(value: str | None) -> bool:
    return value in VALID_GENDERS


def character_gender(speaker: Speaker) -> str | None:
    """'M'/'F'/'N', or None when this character isn't in CHARACTER_GENDERS yet.

    Keys are lowercased character names (or screennames) — i.e. the lowercased
    voice_key of a character-bearing speaker. A speaker with no character identity
    at all (author OOC / pure narration) is 'N': there's no one to gender.
    """
    for name in (speaker.character_name, speaker.screenname):
        if name and name.strip().lower() in CHARACTER_GENDERS:
            return CHARACTER_GENDERS[name.strip().lower()]
    if not speaker.character_name and not speaker.screenname:
        return "N"
    return None
