from glowfic_tts.html_text import parse_paragraphs


def _plain(html: str) -> list[str]:
    return ["".join(run.text for run in para).strip() for para in parse_paragraphs(html)]


def test_plain_paragraphs():
    assert _plain("<p>One.</p><p>Two.</p>") == ["One.", "Two."]


def test_blockquote_paragraphs_are_kept_in_order():
    # <p> nested in a wrapper must not be dropped (regression: post 53995's note)
    html = (
        "<p>She writes Alfirin. The note reads,</p>"
        "<blockquote><p>I'd like to apprentice to you.</p>"
        "<p>I would consider it a favor.</p></blockquote>"
        "<p>It is the kind of note.</p>"
    )
    assert _plain(html) == [
        "She writes Alfirin. The note reads,",
        "I'd like to apprentice to you.",
        "I would consider it a favor.",
        "It is the kind of note.",
    ]


def test_no_paragraph_tags_falls_back_to_whole_root():
    assert _plain("just some bare text") == ["just some bare text"]


def test_wrapper_text_around_nested_paragraph_is_kept():
    # text living directly in a wrapper, beside a nested <p>, must survive
    html = "<blockquote>Intro <p>Quote</p> outro</blockquote>"
    assert _plain(html) == ["Intro", "Quote", "outro"]


def test_list_items_are_separate_paragraphs():
    assert _plain("<ul><li>first</li><li>second</li></ul>") == ["first", "second"]


def test_whitespace_between_inline_tags_is_kept():
    # the space between </em> and <strong> is real, not layout noise
    assert _plain("<p>foo <em>bar</em> <strong>baz</strong></p>") == ["foo bar baz"]


def test_emphasis_and_br_within_a_paragraph():
    [runs] = parse_paragraphs("<p>plain <em>emph</em> after<br>next line</p>")
    assert [(r.text, r.emphasis) for r in runs] == [
        ("plain ", False),
        ("emph", True),
        (" after", False),
        ("\n", False),
        ("next line", False),
    ]
