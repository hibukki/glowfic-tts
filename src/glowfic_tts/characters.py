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
    aliases: list[str] = Field(default_factory=list)  # other (lowercased) names for the same person
    observations: Observations = Field(default_factory=Observations)
    interpretation: Interpretation = Field(default_factory=Interpretation)


def _c(*, gender=None, accent=None, age=None, vibe=None, icon=None, quote=None, aliases=()) -> Character:
    return Character(
        aliases=[a.lower() for a in aliases],
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

    # planecrash / projectlawful — variants collapsed via aliases. Vibes from the
    # user; gender inferred (art/canon) — correct freely.
    "keltham": _c(gender="M", age="17", vibe="punk; dath ilani",
                  aliases=["kelsam", ">keltham", "dath keltham??", "keltham+", "keltham v3", "keltham v4"]),
    "carissa sevar": _c(gender="F", age="~23", vibe="protagonist", aliases=["carissa"]),
    "abrogail": _c(gender="F", vibe="seductive, charismatic, powerful, evil queen of Cheliax",
                   aliases=["rogail", "abrogail thrune ii"]),
    "asmodia": _c(gender="F", vibe="math student"),
    "pilar": _c(gender="F", vibe="submissive student",
                aliases=["pilara pine", "pilara pinedi", "pilar pineda"]),
    "curse of laughter": _c(gender="F", vibe="childish, silly, sing-song (My Little Pony); Pilar's curse"),
    "ione sala": _c(gender="F", vibe="knowledgeable student", aliases=["ione"]),
    # Golarion gods
    "nethys": _c(gender="M", accent="British", vibe="silly, confused (god of magic)"),
    "abadar": _c(gender="M", vibe="banker; fair, calm"),
    "irori": _c(gender="M", vibe="no-ego (god of self-perfection)"),
    "zon-kuthon": _c(gender="M", vibe="scary, evil"),
    "dispater": _c(gender="M", accent="British", vibe="a devil, but very polite and tidy"),
    "cayden cailean": _c(gender="M", vibe="god of getting drunk"),
    "pharasma": _c(gender="F", vibe="goddess of birth, death, fate"),
    "otolmens": _c(gender="F", vibe="enforces the laws of magic"),

    # post 11623 — Dom, Incorporated (reality-show parody): Chad + seven women ("harem")
    "chad roosterman": _c(gender="M", vibe="overconfident himbo entrepreneur; the bachelor/CEO contestant"),
    "jeannie": _c(gender="F", vibe="harem-member employee; formal, deferential"),
    "jade": _c(gender="F", vibe="harem-member employee; nervous, blurts the inconvenient truth"),
    "silver": _c(gender="F", vibe="harem-member employee; silver-haired, amnesiac, deadpan"),
    "iroko": _c(gender="F", vibe="harem-member employee; blunt, keeps forgetting to flirt"),
    "amber": _c(gender="F", vibe="harem-member employee; wants to run the harem"),
    "lychee": _c(gender="F", vibe="harem-member employee"),
    "pansy": _c(gender="F", vibe="harem-member employee; flirty, ditzy"),
    "dom, incorporated": _c(gender="N", vibe="the reality show's hype announcer / narration"),
    "the entreprenettes": _c(gender="N", vibe="the seven women as a group (collective narration)"),

    # post 19583 — planecrash (Westcrown)
    "kobolds": _c(gender="N", vibe="narration: the kobolds beneath Westcrown (collective/setting)"),

    # post 51159 — Mariona Durán (Asmodean Worldwound commander) at an Irorian temple.
    # "minor character N" are the author's placeholder labels (real names in the vibe);
    # generic, so a future post reusing the label would collide — see notes.
    "mariona durán": _c(gender="F", vibe="protagonist; Asmodean priestess / Worldwound commander, intense"),
    "alaric": _c(gender="M", vibe="scary-looking senior Irorian monk"),
    "varan": _c(gender="M", vibe="Irorian monk"),
    "ricard abello": _c(gender="M", vibe="fifth-circle Asmodean, new to Worldwound Fort #14"),
    "dragomir devendra": _c(gender="M", vibe="Irorian temple security/merchant-services official"),
    "minor character": _c(gender="F", vibe="Vesna (near-whisper)"),
    "minor character 2": _c(gender="F", vibe="Valmira (cleric)"),
    "minor character 3": _c(gender="M", vibe="Irorian monk questioning Durán"),
    "security": _c(gender="N", vibe="temple gatekeeper role (institutional flag icon)"),
    "golarion gods": _c(gender="N", vibe="gods as a collective (narration)"),
}


VALID_GENDERS = ("M", "F", "N")


def is_known_gender(value: str | None) -> bool:
    return value in VALID_GENDERS


def _find(speaker: Speaker) -> Character | None:
    names = [n.strip().lower() for n in (speaker.character_name, speaker.screenname) if n]
    for name in names:
        if name in CHARACTERS:
            return CHARACTERS[name]
    for name in names:
        for character in CHARACTERS.values():
            if name in character.aliases:
                return character
    return None


def character_gender(speaker: Speaker) -> str | None:
    """'M'/'F'/'N', or None when this character isn't in CHARACTERS (or has no gender set).

    A speaker with no character identity at all (author OOC / pure narration) is 'N':
    there's no one to gender.
    """
    character = _find(speaker)
    if character:
        return character.interpretation.gender
    if not speaker.character_name and not speaker.screenname:
        return "N"
    return None


def character_accent(speaker: Speaker) -> str | None:
    character = _find(speaker)
    return character.interpretation.accent if character else None
