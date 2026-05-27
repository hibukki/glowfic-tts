"""Command line: one subcommand per pipeline step, plus `all` to run them in order.

    glowfic-tts all 7508 --limit 25            # free/offline render via macOS `say`
    glowfic-tts all 7508 --provider gemini      # full Gemini TTS render
"""

from __future__ import annotations

import argparse

from . import pipeline
from .api import GlowficClient
from .models import Coverage
from .storage import Storage

_STEPS = ["fetch", "assemble", "extract", "voices", "bind", "tts", "concat", "all", "cast"]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="glowfic-tts", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for step in _STEPS:
        sp = sub.add_parser(step)
        sp.add_argument("post_id", type=int)
        sp.add_argument("--limit", type=int, default=None, help="only the first N replies")
        if step in ("tts", "all"):
            sp.add_argument("--provider", default="say", choices=["say", "gemini"])
            sp.add_argument("--api-key", default=None, help="Gemini key (else $GEMINI_API_KEY)")
            sp.add_argument("--workers", type=int, default=None, help="parallel synthesis workers")
        if step in ("concat", "all"):
            sp.add_argument("--group", type=int, default=None, help="one file per N replies")
            sp.add_argument(
                "--chapters", action="store_true",
                help="emit a single output.m4b with a chapter per tag (open in Apple Books)",
            )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    if getattr(args, "group", None) is not None and args.group < 1:
        parser.error("--group must be at least 1")
    storage = Storage(args.post_id, Coverage.of(args.limit))
    provider = getattr(args, "provider", "say")
    api_key = getattr(args, "api_key", None)

    if args.cmd in ("fetch", "all"):
        with GlowficClient() as client:
            raw = pipeline.run_fetch(storage, client, args.post_id, args.limit)
        print(f"fetched {len(raw.replies)} replies -> {storage.dir}/01_raw")
    if args.cmd in ("assemble", "all"):
        story = pipeline.run_assemble(storage)
        print(f"assembled {len(story.segments)} segments")
    if args.cmd in ("extract", "all"):
        script = pipeline.run_extract(storage)
        print(f"extracted {len(script.chunks)} chunks for {len(script.speakers)} speakers")
    if args.cmd in ("voices", "all"):
        voicemap = pipeline.run_voices(storage)
        print(f"voice map ({len(voicemap.voices)} speakers) -> {storage.voices_path}")
    if args.cmd in ("bind", "all"):
        lines = pipeline.run_bind(storage)
        print(f"bound {len(lines.lines)} lines")
    if args.cmd in ("tts", "all"):
        manifest = pipeline.run_tts(storage, provider=provider, api_key=api_key, workers=getattr(args, "workers", None))
        print(f"synthesized {len(manifest.clips)} clips via {provider} -> {storage.audio_dir}")
    if args.cmd in ("concat", "all"):
        if getattr(args, "chapters", False):
            out = pipeline.run_chapters(storage)
            print(f"done -> {out}  (chaptered audiobook — open in Apple Books)")
        else:
            outputs = pipeline.run_concat(storage, group=getattr(args, "group", None))
            print(f"done -> {len(outputs)} file(s):")
            for path in outputs:
                print(f"  {path}")
    if args.cmd == "cast":
        out = pipeline.write_casting_doc(storage)
        print(f"wrote {out}")
        print("Open it — it previews each character's art (most central first). Note each")
        print(f"one's gender/vibe in the art/gender lines, set voices in {storage.voices_path},")
        print(f"then build it:  glowfic-tts all {args.post_id} --chapters")
