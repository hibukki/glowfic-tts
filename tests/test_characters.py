from glowfic_tts.characters import character_gender
from glowfic_tts.models import Speaker


def _speaker(name=None, screenname=None):
    return Speaker(character_id=None, character_name=name, screenname=screenname, username="u")


def test_alias_resolves_a_variant_to_the_same_character():
    assert character_gender(_speaker("Keltham v4", "artifact-headband")) == "M"  # via alias
    assert character_gender(_speaker("Keltham")) == "M"


def test_speaker_with_no_character_is_narration():
    assert character_gender(_speaker()) == "N"


def test_unknown_character_has_no_gender():
    assert character_gender(_speaker("Totally Unknown OC")) is None
