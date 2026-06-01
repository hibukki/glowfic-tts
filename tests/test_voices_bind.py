import pytest

from glowfic_tts.models import GeminiVoice, MacSayVoice, Voice, VoiceMap
from glowfic_tts.stages import (
    MissingGenders,
    NoGenderedVoice,
    assemble,
    bind,
    extract,
    make_voicemap,
)
from glowfic_tts.voices import say_voice_gender


def _n(script):
    """All-narration genders (any voice) — for tests not about gender matching."""
    return {k: "N" for k in script.speakers}


def test_voicemap_covers_every_speaker(raw_post):
    script = extract(assemble(raw_post))
    vm = make_voicemap(script, _n(script))
    assert set(vm.voices) == set(script.speakers)
    assert all(v.gemini for v in vm.voices.values())


def test_voicemap_preserves_user_edits(raw_post):
    script = extract(assemble(raw_post))
    some_key = next(iter(sorted(script.speakers)))
    edited = VoiceMap(voices={some_key: Voice(gemini=GeminiVoice(voice_name="Puck", style_prompt="gravelly"))})

    vm = make_voicemap(script, _n(script), existing=edited)
    assert vm.voices[some_key].gemini.voice_name == "Puck"
    assert vm.voices[some_key].gemini.style_prompt == "gravelly"
    assert set(vm.voices) == set(script.speakers)  # others still filled in


def test_voicemap_is_deterministic(raw_post):
    script = extract(assemble(raw_post))
    assert make_voicemap(script, _n(script)) == make_voicemap(script, _n(script))


def test_distinct_speakers_get_distinct_voices_within_pool(raw_post):
    script = extract(assemble(raw_post))
    assert len(script.speakers) <= 7  # fixture stays within the clear-voice pool
    vm = make_voicemap(script, _n(script))
    say_names = [v.say.voice_name for v in vm.voices.values()]
    assert len(set(say_names)) == len(say_names)  # no collisions


def test_blacklisted_say_voice_is_reassigned_but_other_edits_kept(raw_post):
    script = extract(assemble(raw_post))
    key = sorted(script.speakers)[0]
    stuck = VoiceMap(
        voices={key: Voice(gemini=GeminiVoice(voice_name="Puck"), say=MacSayVoice(voice_name="Fred"))}
    )
    vm = make_voicemap(script, _n(script), existing=stuck, say_blacklist={"Fred"})
    assert vm.voices[key].say.voice_name != "Fred"  # healed
    assert vm.voices[key].gemini.voice_name == "Puck"  # unrelated edit preserved


def test_autocast_refuses_unknown_gender(raw_post):
    script = extract(assemble(raw_post))
    keys = sorted(script.speakers)
    genders = _n(script)
    del genders[keys[0]]  # one speaker with no known gender
    with pytest.raises(MissingGenders) as exc:
        make_voicemap(script, genders)
    assert keys[0] in exc.value.names


def test_naive_autocast_allows_unknown_gender(raw_post):
    script = extract(assemble(raw_post))
    genders = _n(script)
    del genders[sorted(script.speakers)[0]]
    vm = make_voicemap(script, genders, allow_missing=True)
    assert set(vm.voices) == set(script.speakers)


def test_known_gender_gets_a_matching_voice(raw_post):
    script = extract(assemble(raw_post))
    key = sorted(script.speakers)[0]
    genders = _n(script)
    genders[key] = "M"
    vm = make_voicemap(script, genders)
    assert say_voice_gender(vm.voices[key].say.voice_name) == "M"


def test_accent_is_a_soft_preference(raw_post):
    script = extract(assemble(raw_post))
    key = sorted(script.speakers)[0]
    genders = _n(script)
    genders[key] = "M"
    say_voices = ["Daniel (Enhanced)", "Tom (Enhanced)"]  # both M
    voice_accents = {"Daniel (Enhanced)": "British", "Tom (Enhanced)": "American"}

    matched = make_voicemap(script, genders, say_voices=say_voices,
                            accents={key: "British"}, voice_accents=voice_accents)
    assert matched.voices[key].say.voice_name == "Daniel (Enhanced)"  # accent honored

    # soft: an accent with no matching voice still casts (gender-matched), no raise
    fell_back = make_voicemap(script, genders, say_voices=say_voices,
                              accents={key: "Irish"}, voice_accents=voice_accents)
    assert fell_back.voices[key].say.voice_name in say_voices


def test_no_installed_voice_for_gender_fails_loud(raw_post):
    script = extract(assemble(raw_post))
    key = sorted(script.speakers)[0]
    genders = _n(script)
    genders[key] = "M"
    female_only = ["Samantha", "Karen", "Moira", "Tessa"]  # all F in _SAY_GENDER
    with pytest.raises(NoGenderedVoice) as exc:
        make_voicemap(script, genders, say_voices=female_only)
    assert key in exc.value.by_gender["M"]


def test_naive_autocast_substitutes_when_no_gendered_voice(raw_post):
    script = extract(assemble(raw_post))
    key = sorted(script.speakers)[0]
    genders = _n(script)
    genders[key] = "M"
    vm = make_voicemap(script, genders, say_voices=["Samantha", "Karen"], allow_missing=True)
    assert set(vm.voices) == set(script.speakers)  # falls back instead of raising


def test_bind_resolves_each_chunk_to_its_voice(raw_post):
    script = extract(assemble(raw_post))
    vm = make_voicemap(script, _n(script))
    lines = bind(script, vm, announce_first_appearance=False)

    assert len(lines.lines) == len(script.chunks)
    for line, chunk in zip(lines.lines, script.chunks):
        assert line.voice == vm.voices[chunk.voice_key]
        assert line.text == chunk.rich.plain()


def test_characters_introduce_themselves_once_on_first_appearance(raw_post):
    script = extract(assemble(raw_post))
    vm = make_voicemap(script, _n(script))
    vm.voices["Alexeara Cansellarion"].title = "lantalótë"  # user-supplied epithet
    lines = bind(script, vm, announce_first_appearance=True)

    # The intro is its own line (chunk_index -1), exactly the introduction text.
    opening = lines.lines[0]
    assert opening.chunk_index == -1
    assert opening.text == "Alexeara Cansellarion. third-of-that-name. lantalótë."

    # Each named character gets exactly one intro line; content lines are untouched.
    intro_lines = [l for l in lines.lines if l.chunk_index == -1]
    assert len(intro_lines) == len({l.voice_key for l in intro_lines})
    content = [l for l in lines.lines if l.chunk_index >= 0]
    assert len(content) == len(script.chunks)


def test_bind_fails_loudly_on_missing_voice(raw_post):
    script = extract(assemble(raw_post))
    with pytest.raises(KeyError):
        bind(script, VoiceMap(voices={}))
