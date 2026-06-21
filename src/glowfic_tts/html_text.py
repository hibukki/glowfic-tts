"""Glowfic reply HTML -> structured paragraphs of TextRun (emphasis preserved).

Glowfic content is mostly <p> with inline <em>/<strong>, sometimes wrapped in a
<blockquote> (or other container). We walk the whole tree once, starting a new
paragraph at every block-level boundary, so text is never dropped however it's
nested. Unknown tags degrade gracefully: we keep their text and drop the tag.
"""

from __future__ import annotations

import lxml.html

from .models import TextRun

_EMPHASIS_TAGS = {"em", "i"}
_STRONG_TAGS = {"strong", "b"}
# Tags that end the current paragraph and begin a new one. <br> is NOT here: it's
# a soft line break kept inside the paragraph.
_BLOCK_TAGS = {
    "p", "blockquote", "div", "section", "article", "li", "ul", "ol",
    "h1", "h2", "h3", "h4", "h5", "h6",
}


def _clean(text: str) -> str:
    return text.replace("\xa0", " ")  # &nbsp; -> normal space


def _image_note(img) -> str:
    # images are embedded in the prose; a listener can't see them, so speak a note
    alt = _clean((img.get("alt") or "").strip())
    return f"Audio note, image: {alt}." if alt else "Audio note: there's an image here."


def _walk(node, emphasis: bool, strong: bool, paragraphs: list[list[TextRun]]) -> None:
    tag = node.tag if isinstance(node.tag, str) else ""
    if tag in _BLOCK_TAGS:
        paragraphs.append([])
    current = paragraphs[-1]

    here_em = emphasis or tag in _EMPHASIS_TAGS
    here_strong = strong or tag in _STRONG_TAGS

    if tag == "br":
        current.append(TextRun(text="\n"))
    if tag == "img":
        current.append(TextRun(text=_image_note(node)))
    if node.text:
        current.append(TextRun(text=_clean(node.text), emphasis=here_em, strong=here_strong))

    for child in node:
        _walk(child, here_em, here_strong, paragraphs)
        if not child.tail:  # `.tail` is text after the child, still inside `node`
            continue
        if isinstance(child.tag, str) and child.tag in _BLOCK_TAGS:
            if not child.tail.strip():
                continue  # whitespace between blocks (e.g. "\r\n") — layout, not content
            paragraphs.append([])  # real tail after a closed block -> its own paragraph
        # an inline child's tail (incl. a lone space between <em>/<strong>) is content
        paragraphs[-1].append(TextRun(text=_clean(child.tail), emphasis=emphasis, strong=strong))


def parse_paragraphs(html: str) -> list[list[TextRun]]:
    """Return one run-list per paragraph; empty/whitespace-only paragraphs are dropped."""
    root = lxml.html.fromstring(f"<div>{html}</div>")
    paragraphs: list[list[TextRun]] = [[]]
    _walk(root, emphasis=False, strong=False, paragraphs=paragraphs)
    return [runs for runs in paragraphs if any(run.text.strip() for run in runs)]
