import pytest

from glowfic_tts.models import GeminiVoice, Voice, VoiceMap
from glowfic_tts.stages import assemble, bind, extract, make_voicemap


def test_voicemap_covers_every_speaker(raw_post):
    script = extract(assemble(raw_post))
    vm = make_voicemap(script)
    assert set(vm.voices) == set(script.speakers)
    assert all(v.gemini for v in vm.voices.values())


def test_voicemap_preserves_user_edits(raw_post):
    script = extract(assemble(raw_post))
    some_key = next(iter(sorted(script.speakers)))
    edited = VoiceMap(voices={some_key: Voice(gemini=GeminiVoice(voice_name="Puck", style_prompt="gravelly"))})

    vm = make_voicemap(script, existing=edited)
    assert vm.voices[some_key].gemini.voice_name == "Puck"
    assert vm.voices[some_key].gemini.style_prompt == "gravelly"
    assert set(vm.voices) == set(script.speakers)  # others still filled in


def test_voicemap_is_deterministic(raw_post):
    script = extract(assemble(raw_post))
    assert make_voicemap(script) == make_voicemap(script)


def test_bind_resolves_each_chunk_to_its_voice(raw_post):
    script = extract(assemble(raw_post))
    vm = make_voicemap(script)
    lines = bind(script, vm)

    assert len(lines.lines) == len(script.chunks)
    for line, chunk in zip(lines.lines, script.chunks):
        assert line.voice == vm.voices[chunk.voice_key]
        assert line.text == chunk.rich.plain()


def test_bind_fails_loudly_on_missing_voice(raw_post):
    script = extract(assemble(raw_post))
    with pytest.raises(KeyError):
        bind(script, VoiceMap(voices={}))
