"""Fixtures are real captured API responses, so these double as drift detection:
if the live schema changes incompatibly, model_validate in conftest fails."""

from glowfic_tts.stages import assemble


def test_opening_post_is_seq_zero_then_replies_in_order(raw_post):
    story = assemble(raw_post)

    assert story.post_id == 7508
    assert [s.seq for s in story.segments] == list(range(len(raw_post.replies) + 1))

    opening = story.segments[0]
    assert opening.reply_id is None
    assert opening.content_html == raw_post.post.content

    for segment, reply in zip(story.segments[1:], raw_post.replies):
        assert segment.reply_id == reply.id
        assert segment.content_html == reply.content


def test_every_segment_has_a_resolvable_voice_key(raw_post):
    story = assemble(raw_post)
    assert all(s.speaker.voice_key for s in story.segments)


def test_opening_uses_character_not_author_fallback(raw_post):
    # The opening post has a character, so its voice_key must be the character
    # name, never the "@username" fallback.
    opening = assemble(raw_post).segments[0]
    assert opening.speaker.voice_key == raw_post.post.character.name
    assert not opening.speaker.voice_key.startswith("@")
