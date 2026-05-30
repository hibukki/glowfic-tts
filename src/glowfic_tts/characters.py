"""What we know about each character — the cross-story source of truth.

NOT where voices are picked: a character can be central (Premium voice) in one
post and minor in another, so the per-post pick lives with that post (voices.toml),
never duplicated here. Here we keep durable, cross-story knowledge that *informs*
the pick, split into what we **observed** (evidence) and how we **interpret** it.
Most is free text for a human (or later an LLM); only `gender` is consumed by
autocast today (drives voice gender-matching) — `accent` is the natural next match.

Autocast won't guess gender: a character with no 'M'/'F'/'N' here fails the build
with a worklist (the casting preview shows their art + opening line to help decide).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .models import Speaker


class Observations(BaseModel):
    """Evidence, straight from the source — no interpretation."""

    icons: list[str] = Field(default_factory=list)   # art links seen for this character
    quotes: list[str] = Field(default_factory=list)  # lines from their first appearances


class Interpretation(BaseModel):
    """How we read the character. Free text except `gender`."""

    gender: str | None = None   # "M" / "F" / "N"
    accent: str | None = None   # e.g. "British", "Indian"
    age: str | None = None      # e.g. "young adult", "elderly"
    vibe: str | None = None     # e.g. "tough", "funny/confused/comedian, deadpan"


class Character(BaseModel):
    observations: Observations = Field(default_factory=Observations)
    interpretation: Interpretation = Field(default_factory=Interpretation)


def _c(*, gender=None, accent=None, age=None, vibe=None, icon=None, quote=None) -> Character:
    return Character(
        observations=Observations(icons=[icon] if icon else [], quotes=[quote] if quote else []),
        interpretation=Interpretation(gender=gender, accent=accent, age=age, vibe=vibe),
    )


# Keys are lowercased character names (or screennames) — i.e. the lowercased
# voice_key of a character-bearing speaker.
CHARACTERS: dict[str, Character] = {
    # post 53182 — paths we seek in vain
    "merrin": _c(
        gender="F", age="young woman", vibe="careful, optimizing, frantic competence",
        icon="https://d1anwqy6ci9o1i.cloudfront.net/users%2F265%2Ficons%2Fztdriiozx2o8h2e3yn25pk_merrin9.jpeg",
        quote="Even with all the highly optimized insulation and ventilation that Merrin has managed so far…",
    ),
    "vicar esta": _c(
        gender="M", age="older man", vibe="intense, menacing Chelish vicar; bald, grey-black beard",
        icon="https://d1anwqy6ci9o1i.cloudfront.net/users%2F366%2Ficons%2F0190yufc2zjiscvo0knofr_Screenshot+2026-01-02+195454.png",
        quote="Vicar Esta will after recent events be Stunned for several rounds and Discombobulated…",
    ),
    "laeirthe": _c(
        gender="M", vibe="catfolk man, long blonde hair, bearded",
        icon="https://d1anwqy6ci9o1i.cloudfront.net/users%2F265%2Ficons%2Fy29jgw783m9nwvh72v9xn_mornelithe7.png",
        quote="Merrin. Hey. Merrin.",
    ),
    "asmodeus": _c(
        gender="M", vibe="a god; casual, amused menace",
        icon="https://d1anwqy6ci9o1i.cloudfront.net/users%2F34%2Ficons%2Fvji9m2s8dihkc6l2oswi6_Screen+Shot+2020-09-11+at+8.26.10+PM.png",
        quote="WOW that squirrel has gotten itself lost. Asmodeus can, like, barely hear it from here.",
    ),
    "aspexia rugatonn": _c(
        gender="F", age="older woman", vibe="Grand High Priestess of Asmodeus; steely",
        icon="https://d1anwqy6ci9o1i.cloudfront.net/users%2F366%2Ficons%2F41pkf0zzhsfepwk67lg95m_rugatonn.png",
        quote="Just commit to not using the Bag's contents if you find them, idiot…",
    ),
    # narration / settings — no single gender, any voice
    "dath ilan": _c(gender="N", vibe="narration: dath ilan worldview (Exception Handling, optimization)"),
    "places": _c(gender="N", vibe="scene / cosmology narration (River of Souls map)"),
    "unnamed exoplanet": _c(gender="N", vibe="environmental/log narration"),
    "cheliax": _c(gender="N", vibe="the nation as narrator"),
    "various gods": _c(gender="N", vibe="assorted deities narration"),
}


VALID_GENDERS = ("M", "F", "N")


def is_known_gender(value: str | None) -> bool:
    return value in VALID_GENDERS


def character_gender(speaker: Speaker) -> str | None:
    """'M'/'F'/'N', or None when this character isn't in CHARACTERS (or has no gender set).

    A speaker with no character identity at all (author OOC / pure narration) is 'N':
    there's no one to gender.
    """
    for name in (speaker.character_name, speaker.screenname):
        if name and name.strip().lower() in CHARACTERS:
            return CHARACTERS[name.strip().lower()].interpretation.gender
    if not speaker.character_name and not speaker.screenname:
        return "N"
    return None
