from glowfic_tts.models import (
    Coverage,
    GeminiVoice,
    RichText,
    Speaker,
    SynthSpec,
    TextRun,
    Voice,
)


def test_coverage_slug():
    assert Coverage.of(None).slug() == "full"
    assert Coverage.of(25).slug() == "limit_25"


def test_zero_limit_is_not_treated_as_full():
    # Regression: limit 0 must not collide with the full-run path.
    assert Coverage.of(0).kind == "limit"
    assert Coverage.of(0).slug() == "limit_0"
    assert Coverage.of(0) != Coverage.of(None)


def test_voice_key_prefers_character_then_author():
    char = Speaker(character_id=1, character_name="Iomedae", screenname=None, username="lintamande")
    assert char.voice_key == "Iomedae"

    narrator = Speaker(character_id=None, character_name=None, screenname=None, username="alicorn")
    assert narrator.voice_key == "@alicorn"


def test_richtext_plain_drops_formatting():
    rich = RichText(runs=[TextRun(text="She "), TextRun(text="ran", emphasis=True), TextRun(text=".")])
    assert rich.plain() == "She ran."


def _spec(**overrides) -> SynthSpec:
    base = dict(
        provider="gemini",
        model="gemini-2.5-flash-preview-tts",
        voice=Voice(gemini=GeminiVoice(voice_name="Kore")),
        output_format="wav",
        text="Hello there.",
    )
    base.update(overrides)
    return SynthSpec(**base)


def test_synthspec_key_is_stable_for_identical_input():
    assert _spec().key() == _spec().key()


def test_synthspec_key_changes_when_anything_changes():
    base = _spec().key()
    assert _spec(text="Different.").key() != base
    assert _spec(voice=Voice(gemini=GeminiVoice(voice_name="Puck"))).key() != base
    assert _spec(output_format="mp3").key() != base
    assert _spec(params={"speed": 1.2}).key() != base
    assert _spec(model="other").key() != base
