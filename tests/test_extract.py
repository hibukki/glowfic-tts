from glowfic_tts.html_text import parse_paragraphs
from glowfic_tts.models import Coverage, Segment, Speaker, Story
from glowfic_tts.stages import assemble, extract


def _story_from(html: str) -> Story:
    speaker = Speaker(character_id=1, character_name="Iomedae", screenname=None, username="lin")
    return Story(
        coverage=Coverage.of(None),
        post_id=1,
        subject="t",
        authors=[speaker],
        segments=[Segment(seq=0, reply_id=None, speaker=speaker, icon_keyword=None, content_html=html)],
    )


def test_emphasis_is_preserved_and_text_flattens():
    paragraphs = parse_paragraphs("<p>She <em>ran</em> home.&nbsp;</p>")
    runs = paragraphs[0]
    assert "".join(r.text for r in runs) == "She ran home. "
    assert [r.emphasis for r in runs] == [False, True, False]


def test_multiple_paragraphs_split_into_separate_blocks():
    assert len(parse_paragraphs("<p>One.</p><p>Two.</p>")) == 2


def test_image_becomes_spoken_note_with_alt():
    [runs] = parse_paragraphs('<p><img src="x.png" alt="a starmap"></p>')
    assert "".join(r.text for r in runs) == "Audio note, image: a starmap."


def test_image_without_alt_becomes_generic_note():
    [runs] = parse_paragraphs('<p>Look:<img src="x.png" alt=""></p>')
    assert "".join(r.text for r in runs) == "Look:Audio note: there's an image here."


def test_chunk_voice_key_matches_source_speaker(raw_post):
    # Review fix #1: the speaker must survive extraction; no guessing from seq.
    story = assemble(raw_post)
    by_seq = {s.seq: s.speaker.voice_key for s in story.segments}
    script = extract(story)
    assert script.chunks  # sanity
    for chunk in script.chunks:
        assert chunk.voice_key == by_seq[chunk.seq]
    assert set(script.speakers) == {c.voice_key for c in script.chunks}


def test_long_content_is_chunked_under_limit():
    long_html = "".join(f"<p>Sentence number {i} here.</p>" for i in range(200))
    script = extract(_story_from(long_html), max_chars=200)
    assert len(script.chunks) > 1
    assert all(len(c.rich.plain()) <= 200 for c in script.chunks)
    # Nothing is lost: every paragraph's text still appears across the chunks.
    joined = " ".join(c.rich.plain() for c in script.chunks)
    assert "Sentence number 0 here." in joined and "Sentence number 199 here." in joined
