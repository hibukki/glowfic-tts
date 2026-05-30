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


def character_gender(speaker: Speaker) -> str | None:
    """'M'/'F'/'N', or None when the character isn't in CHARACTER_GENDERS yet."""
    if not speaker.character_name:
        return "N"  # author OOC / pure narration: no character, no gender to pick
    return CHARACTER_GENDERS.get(speaker.character_name.strip().lower())
