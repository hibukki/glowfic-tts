import io
import wave

import pytest

from glowfic_tts import pipeline
from glowfic_tts.api import PageMeta, RawApiPost, RawApiReply, RawCharacter, RawPost, RawUser
from glowfic_tts.models import (
    AudioClip,
    AudioManifest,
    Coverage,
    Line,
    Lines,
    MacSayVoice,
    Story,
    SynthSpec,
    Voice,
)
from glowfic_tts.storage import Storage


def _tiny_wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x00\x00" * 2400)  # 0.1s of silence
    return buf.getvalue()


class FakeClient:
    def __init__(self, post: RawApiPost, pages: list[list[RawApiReply]]):
        self.post = post
        self.pages = pages
        self.post_calls = 0
        self.page_calls: list[int] = []

    def get_post(self, post_id):
        self.post_calls += 1
        return self.post

    def get_replies_page(self, post_id, page, per_page):
        self.page_calls.append(page)
        items = self.pages[page - 1]
        return items, PageMeta(page=page, per_page=per_page, total=sum(len(p) for p in self.pages))


def _reply(i: int) -> RawApiReply:
    return RawApiReply(id=i, content=f"<p>line {i}</p>", user=RawUser(username="u"))


def _post() -> RawApiPost:
    return RawApiPost(id=7, subject="s", authors=[RawUser(username="u")], num_replies=10, content="<p>start</p>")


def test_fetch_respects_limit_and_caches(tmp_path):
    storage = Storage(7, Coverage.of(3), root=tmp_path)
    client = FakeClient(_post(), [[_reply(i) for i in range(1, 11)]])  # one big page available

    raw = pipeline.run_fetch(storage, client, 7, limit=3)
    assert len(raw.replies) == 3  # truncated to the limit
    assert client.post_calls == 1

    # rerun: everything cached, zero network
    client.post_calls = 0
    client.page_calls.clear()
    raw2 = pipeline.run_fetch(storage, client, 7, limit=3)
    assert len(raw2.replies) == 3
    assert client.post_calls == 0 and client.page_calls == []


def test_cast_runs_its_prerequisites_from_scratch(tmp_path):
    # The README presents `cast` as the first command; it must work from an empty
    # data dir by running fetch->assemble->extract->voices itself (no manual chain).
    storage = Storage(7, Coverage.of(None), root=tmp_path)
    client = FakeClient(_post(), [[_reply(i) for i in range(1, 4)]])

    pipeline.ensure_casting_inputs(storage, client=client)
    out = pipeline.write_casting_doc(storage)

    assert out.exists()  # casting preview written, no FileNotFoundError
    assert storage.voices_path.exists()  # voices.toml created (post is fully castable)
    assert out.read_text().lstrip().startswith("# Casting")


def test_cast_holds_off_voices_when_a_gender_is_unknown(tmp_path):
    # A character with no gender in characters.py: cast still previews, but must NOT
    # persist a half-cast voices.toml that bind/tts would then trust.
    storage = Storage(8, Coverage.of(None), root=tmp_path)
    stranger = RawApiReply(
        id=1, content="<p>hi</p>",
        character=RawCharacter(id=1, name="Nobody In Characters Py"),
        user=RawUser(username="u"),
    )
    pipeline.ensure_casting_inputs(storage, client=FakeClient(_post(), [[stranger]]))

    assert pipeline.write_casting_doc(storage).exists()
    assert "Nobody In Characters Py" in pipeline.unknown_gender_speakers(storage)
    assert not storage.voices_path.exists()


def test_coverage_isolation_paths_differ(tmp_path):
    assert Storage(7, Coverage.of(None), root=tmp_path).dir != Storage(7, Coverage.of(25), root=tmp_path).dir


def test_load_rejects_mismatched_coverage(tmp_path):
    storage = Storage(7, Coverage.of(25), root=tmp_path)
    full_story = Story(coverage=Coverage.of(None), post_id=7, subject="x", authors=[], segments=[])
    storage._save(storage._path_for(Story), full_story)
    with pytest.raises(ValueError):
        storage.load_story()


def _line(seq: int, voice_name: str, text: str) -> Line:
    voice = Voice(say=MacSayVoice(voice_name=voice_name))
    return Line(seq=seq, chunk_index=0, voice_key=voice_name, voice=voice, text=text)


def test_tts_caches_identical_specs_and_invalidates_on_change(tmp_path, monkeypatch):
    storage = Storage(7, Coverage.of(3), root=tmp_path)
    lines = Lines(
        coverage=storage.coverage,
        post_id=7,
        lines=[
            _line(0, "Samantha", "Hello."),
            _line(1, "Samantha", "Hello."),  # identical fingerprint -> reuse
            _line(2, "Daniel", "Hello."),  # different voice -> new clip
        ],
    )
    storage.save(lines)

    calls: list[str] = []

    def fake_synth(spec: SynthSpec) -> bytes:
        calls.append(spec.key())
        return _tiny_wav()

    monkeypatch.setattr(pipeline, "_provider", lambda provider, api_key: (fake_synth, "say"))
    monkeypatch.setattr(pipeline, "installed_quality_say_voices", lambda: ["Samantha", "Daniel"])

    manifest = pipeline.run_tts(storage)
    assert len(manifest.clips) == 3
    assert len(calls) == 2  # two unique fingerprints, not three
    assert len({c.synthesis_key for c in manifest.clips}) == 2

    calls.clear()
    pipeline.run_tts(storage)  # rerun: all cached
    assert calls == []


def test_say_tts_requires_quality_voices(tmp_path, monkeypatch):
    storage = Storage(7, Coverage.of(1), root=tmp_path)
    storage.save(Lines(coverage=storage.coverage, post_id=7, lines=[_line(0, "Samantha", "Hi.")]))
    monkeypatch.setattr(pipeline, "installed_quality_say_voices", lambda: [])  # none installed
    with pytest.raises(RuntimeError, match="Enhanced/Premium"):
        pipeline.run_tts(storage, provider="say")


def test_concat_orders_clips_by_seq(tmp_path):
    storage = Storage(7, Coverage.of(2), root=tmp_path)
    storage.audio_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for seq in (0, 1):
        p = storage.audio_dir / f"clip{seq}.wav"
        p.write_bytes(_tiny_wav())
        paths.append(p)

    # manifest deliberately out of order; concat must sort by (seq, chunk_index)
    manifest = AudioManifest(
        coverage=storage.coverage,
        post_id=7,
        clips=[
            AudioClip(seq=1, chunk_index=0, synthesis_key="b", spec=_spec("two"), path=str(paths[1])),
            AudioClip(seq=0, chunk_index=0, synthesis_key="a", spec=_spec("one"), path=str(paths[0])),
        ],
    )
    storage.save(manifest)

    outputs = pipeline.run_concat(storage)
    assert len(outputs) == 1 and outputs[0].exists() and outputs[0].stat().st_size > 0


def test_concat_to_wav_sums_frames_and_rejects_mismatch(tmp_path):
    a, b = tmp_path / "a.wav", tmp_path / "b.wav"
    a.write_bytes(_tiny_wav())
    b.write_bytes(_tiny_wav())
    combined = pipeline._concat_to_wav([a, b], tmp_path / "out.wav")
    with wave.open(str(a)) as wa, wave.open(str(combined)) as wc:
        assert wc.getnframes() == 2 * wa.getnframes()
        assert wc.getframerate() == wa.getframerate()

    odd = tmp_path / "odd.wav"
    with wave.open(str(odd), "wb") as w:  # different rate -> must refuse
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes(b"\x00\x00" * 100)
    with pytest.raises(ValueError):
        pipeline._concat_to_wav([a, odd], tmp_path / "bad.wav")


def test_concat_groups_into_files_by_reply_range(tmp_path):
    storage = Storage(7, Coverage.of(4), root=tmp_path)
    storage.audio_dir.mkdir(parents=True, exist_ok=True)
    clips = []
    for seq in range(4):
        p = storage.audio_dir / f"clip{seq}.wav"
        p.write_bytes(_tiny_wav())
        clips.append(AudioClip(seq=seq, chunk_index=0, synthesis_key=str(seq), spec=_spec(str(seq)), path=str(p)))
    storage.save(AudioManifest(coverage=storage.coverage, post_id=7, clips=clips))

    outputs = pipeline.run_concat(storage, group=2)
    names = sorted(p.name for p in outputs)
    assert names == ["output_seq_0000_to_0001.mp3", "output_seq_0002_to_0003.mp3"]
    assert all(p.exists() and p.stat().st_size > 0 for p in outputs)


def test_chapters_one_per_tag_with_titles(tmp_path):
    storage = Storage(7, Coverage.of(2), root=tmp_path)
    storage.audio_dir.mkdir(parents=True, exist_ok=True)
    clips = []
    for seq in range(2):
        p = storage.audio_dir / f"clip{seq}.wav"
        p.write_bytes(_tiny_wav())
        clips.append(AudioClip(seq=seq, chunk_index=0, synthesis_key=str(seq), spec=_spec(str(seq)), path=str(p)))
    storage.save(AudioManifest(coverage=storage.coverage, post_id=7, clips=clips))
    storage.save(Lines(coverage=storage.coverage, post_id=7, lines=[
        _line(0, "Alex", "Hello there friend."), _line(1, "Bea", "Reply text here."),
    ]))

    out = pipeline.run_chapters(storage)
    assert out.exists() and out.suffix == ".m4b" and out.stat().st_size > 0
    meta = (storage.dir / "_chapters.txt").read_text()
    assert meta.count("[CHAPTER]") == 2
    assert "title=0000 Alex: Hello there friend." in meta


def test_export_publishes_titled_m4b_into_book_folder(tmp_path):
    storage = Storage(7, Coverage.of(None), root=tmp_path)
    storage.dir.mkdir(parents=True, exist_ok=True)
    (storage.dir / "output.m4b").write_bytes(b"fake m4b")
    storage.save(RawPost(
        coverage=storage.coverage,
        post=RawApiPost(id=7, subject="Come, give me my soul: A/B?", authors=[RawUser(username="u")],
                        num_replies=1, content="<p>x</p>"),  # no icon -> no cover, no network
        replies=[],
    ))

    book_dir = pipeline.run_export(storage, tmp_path / "Audiobooks")

    # reserved chars (: / ?) stripped from the Smart-Audiobook-Player folder + file name
    assert book_dir == tmp_path / "Audiobooks" / "Come, give me my soul AB"
    assert (book_dir / "Come, give me my soul AB.m4b").read_bytes() == b"fake m4b"


def test_export_falls_back_to_post_id_when_title_is_all_reserved(tmp_path):
    storage = Storage(7, Coverage.of(None), root=tmp_path)
    storage.dir.mkdir(parents=True, exist_ok=True)
    (storage.dir / "output.m4b").write_bytes(b"m")
    storage.save(RawPost(
        coverage=storage.coverage,
        post=RawApiPost(id=7, subject="??? / ???", authors=[RawUser(username="u")],
                        num_replies=1, content="<p>x</p>"),
        replies=[],
    ))

    book_dir = pipeline.run_export(storage, tmp_path / "Audiobooks")

    # all chars stripped -> safe fallback, not a nested path from the raw title
    assert book_dir == tmp_path / "Audiobooks" / "post-7"
    assert (book_dir / "post-7.m4b").exists()


def test_export_requires_a_built_m4b(tmp_path):
    storage = Storage(7, Coverage.of(None), root=tmp_path)
    with pytest.raises(FileNotFoundError, match="--chapters"):
        pipeline.run_export(storage, tmp_path / "Audiobooks")


def _spec(text: str) -> SynthSpec:
    return SynthSpec(
        provider="say", model="say", voice=Voice(say=MacSayVoice(voice_name="Samantha")),
        output_format="wav", text=text,
    )
