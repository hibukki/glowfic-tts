"""Command line: one subcommand per pipeline step, plus `all` to run them in order.

    glowfic-tts all 7508 --limit 25            # free/offline render via macOS `say`
    glowfic-tts all 7508 --provider gemini      # full Gemini TTS render
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from . import pipeline
from .api import client_from_env
from .models import Coverage
from .stages import CastingError
from .storage import Storage

_STEPS = ["fetch", "assemble", "extract", "voices", "bind", "tts", "concat", "export", "all", "cast"]

_EXPORT_DIR_ENV = "GLOWFIC_AUDIOBOOKS_DIR"


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
        if step in ("voices", "all"):
            sp.add_argument(
                "--dangerously-naive-autocast", action="store_true",
                help="assign voices even for characters with no gender in characters.py",
            )
        if step in ("concat", "all"):
            sp.add_argument("--group", type=int, default=None, help="one file per N replies")
            sp.add_argument(
                "--chapters", action="store_true",
                help="emit a single output.m4b with a chapter per tag (open in Apple Books)",
            )
        if step in ("export", "all"):
            sp.add_argument(
                "--to", default=None,
                help=f"export the .m4b into <dir>/<Book Title>/ (default ${_EXPORT_DIR_ENV})",
            )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    if getattr(args, "group", None) is not None and args.group < 1:
        parser.error("--group must be at least 1")
    export_root = getattr(args, "to", None) or os.environ.get(_EXPORT_DIR_ENV)
    if args.cmd == "all" and export_root and not args.chapters:
        parser.error("--to/$GLOWFIC_AUDIOBOOKS_DIR exports the .m4b, so `all` needs --chapters")
    storage = Storage(args.post_id, Coverage.of(args.limit))
    provider = getattr(args, "provider", "say")
    api_key = getattr(args, "api_key", None)

    if args.cmd in ("fetch", "all"):
        with client_from_env() as client:
            raw = pipeline.run_fetch(storage, client, args.post_id, args.limit)
        print(f"fetched {len(raw.replies)} replies -> {storage.dir}/01_raw")
    if args.cmd in ("assemble", "all"):
        story = pipeline.run_assemble(storage)
        print(f"assembled {len(story.segments)} segments")
    if args.cmd in ("extract", "all"):
        script = pipeline.run_extract(storage)
        print(f"extracted {len(script.chunks)} chunks for {len(script.speakers)} speakers")
    if args.cmd in ("voices", "all"):
        try:
            voicemap = pipeline.run_voices(storage, allow_missing=args.dangerously_naive_autocast)
        except CastingError as e:
            print(f"✋ autocast stopped — {e}")
            print(f"   preview (art + opening lines): {pipeline.write_casting_doc(storage)}")
            print("   ...or build anyway with --dangerously-naive-autocast.")
            raise SystemExit(1)
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
    if args.cmd == "export" or (args.cmd == "all" and export_root):
        if not export_root:
            parser.error(f"export needs a destination: pass --to <dir> or set ${_EXPORT_DIR_ENV}")
        book_dir = pipeline.run_export(storage, Path(export_root))
        print(f"exported -> {book_dir}  (sync this folder to your phone's /Audiobooks/)")
    if args.cmd == "cast":
        print(f"preparing post {args.post_id} (fetch/assemble/extract/voices; cached after the first run)…")
        pipeline.ensure_casting_inputs(storage)
        out = pipeline.write_casting_doc(storage)
        print(f"wrote {out}")
        missing = pipeline.unknown_gender_speakers(storage)
        if missing:
            print("\n⚠️  No gender in characters.py for: " + ", ".join(missing))
            print("   Open the preview for each one's art + opening line, add them to")
            print("   CHARACTERS in characters.py, then build it.")
        else:
            print("Open the preview to check the casting, then build it:")
        print(f"  glowfic-tts all {args.post_id} --chapters")
