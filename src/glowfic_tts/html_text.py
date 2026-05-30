"""Glowfic reply HTML -> structured paragraphs of TextRun (emphasis preserved).

Glowfic content is mostly <p> with inline <em>/<strong>. Unknown tags degrade
gracefully: we keep their text and drop the tag.
"""

from __future__ import annotations

import lxml.html

from .models import TextRun

_EMPHASIS_TAGS = {"em", "i"}
_STRONG_TAGS = {"strong", "b"}


def _clean(text: str) -> str:
    return text.replace("\xa0", " ")  # &nbsp; -> normal space


def _image_note(img) -> str:
    # images are embedded in the prose; a listener can't see them, so speak a note
    alt = _clean((img.get("alt") or "").strip())
    return f"Audio note, image: {alt}." if alt else "Audio note: there's an image here."


def _walk(node, emphasis: bool, strong: bool, runs: list[TextRun]) -> None:
    tag = node.tag if isinstance(node.tag, str) else ""
    here_em = emphasis or tag in _EMPHASIS_TAGS
    here_strong = strong or tag in _STRONG_TAGS

    if tag == "br":
        runs.append(TextRun(text="\n"))
    if tag == "img":
        runs.append(TextRun(text=_image_note(node)))
    if node.text:
        runs.append(TextRun(text=_clean(node.text), emphasis=here_em, strong=here_strong))

    for child in node:
        _walk(child, here_em, here_strong, runs)
        if child.tail:  # text after the child, still inside `node`
            runs.append(TextRun(text=_clean(child.tail), emphasis=emphasis, strong=strong))


def parse_paragraphs(html: str) -> list[list[TextRun]]:
    """Return one run-list per paragraph; empty paragraphs are dropped."""
    root = lxml.html.fromstring(f"<div>{html}</div>")
    blocks = root.findall("p")
    sources = blocks if blocks else [root]

    paragraphs: list[list[TextRun]] = []
    for block in sources:
        runs: list[TextRun] = []
        _walk(block, emphasis=False, strong=False, runs=runs)
        if any(run.text.strip() for run in runs):
            paragraphs.append(runs)
    return paragraphs
