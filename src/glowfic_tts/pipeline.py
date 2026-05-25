"""Orchestrator: owns the cache loops, all disk IO, and stage sequencing.

Each `run_*` loads its inputs via Storage, calls a pure stage (or a network
adapter), and saves the result. Fetch and TTS are cache loops: hit the network
only on a miss, write the artifact, move on (Review fix #4).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from . import stages
from .api import GlowficClient, RawPost
from .models import AudioClip, AudioManifest, Lines, SynthSpec
from .storage import Storage
from .tts import Synth, make_gemini_synth, synth_say
from .voices import (
    GEMINI_TTS_MODEL,
    MAC_SAY_VOICES,
    SAY_INSTALL_HELP,
    installed_quality_say_voices,
)

DEFAULT_PER_PAGE = 100


def run_fetch(storage: Storage, client: GlowficClient, post_id: int, limit: int | None) -> RawPost:
    if storage.raw_post_path.exists():
        post = storage.load_raw_post()
    else:
        post = client.get_post(post_id)
        storage.save_raw_post(post)

    per_page = limit if (limit and limit < DEFAULT_PER_PAGE) else DEFAULT_PER_PAGE
    replies = []
    page = 1
    while True:
        if storage.raw_page_path(page).exists():
            page_items = storage.load_raw_page(page)
        else:
            page_items, _meta = client.get_replies_page(post_id, page, per_page)
            storage.save_raw_page(page, page_items)
        replies.extend(page_items)
        reached_limit = limit is not None and len(replies) >= limit
        if reached_limit or len(page_items) < per_page:
            break
        page += 1

    if limit is not None:
        replies = replies[:limit]
    raw = RawPost(coverage=storage.coverage, post=post, replies=replies)
    storage.save(raw)
    return raw


def run_assemble(storage: Storage):
    story = stages.assemble(storage.load_raw())
    storage.save(story)
    return story


def run_extract(storage: Storage):
    script = stages.extract(storage.load_story())
    storage.save(script)
    return script


def run_voices(storage: Storage):
    # Prefer installed Enhanced/Premium voices; fall back to the standard list so
    # the map still generates (e.g. for gemini-only use). `say` tts enforces quality.
    say_voices = installed_quality_say_voices() or MAC_SAY_VOICES
    voicemap = stages.make_voicemap(
        storage.load_script(), existing=storage.load_voicemap(), say_voices=say_voices
    )
    storage.save_voicemap(voicemap)
    return voicemap


def run_bind(storage: Storage):
    voicemap = storage.load_voicemap()
    if voicemap is None:
        raise FileNotFoundError(f"{storage.voices_path} missing; run `voices` first.")
    lines = stages.bind(storage.load_script(), voicemap)
    storage.save(lines)
    return lines


def _provider(provider: str, api_key: str | None) -> tuple[Synth, str]:
    """Return the synth callable and the model id that goes into the cache key."""
    if provider == "say":
        return synth_say, "say"
    if provider == "gemini":
        return make_gemini_synth(api_key), GEMINI_TTS_MODEL
    raise ValueError(f"Unknown provider {provider!r} (use 'say' or 'gemini').")


def _require_quality_say_voices(lines: Lines) -> None:
    quality = set(installed_quality_say_voices())
    configured = {line.voice.say.voice_name for line in lines.lines if line.voice.say}
    missing = sorted(configured - quality)
    if missing:
        raise RuntimeError(
            "The `say` provider needs Enhanced/Premium voices, but these aren't "
            f"installed (or aren't high-quality): {missing}\n\n{SAY_INSTALL_HELP}\n"
            "After installing, re-run `voices` to reassign, then `tts`."
        )


def run_tts(storage: Storage, provider: str = "say", api_key: str | None = None) -> AudioManifest:
    synth, model = _provider(provider, api_key)
    lines: Lines = storage.load_lines()
    if provider == "say":
        _require_quality_say_voices(lines)
    storage.audio_dir.mkdir(parents=True, exist_ok=True)

    clips = []
    for line in lines.lines:
        spec = SynthSpec(
            provider=provider,
            model=model,
            voice=line.voice,
            output_format="wav",
            text=line.text,
        )
        clip_path = storage.audio_dir / f"{spec.key()}.wav"
        if not clip_path.exists():
            clip_path.write_bytes(synth(spec))
        clips.append(
            AudioClip(
                seq=line.seq,
                chunk_index=line.chunk_index,
                synthesis_key=spec.key(),
                spec=spec,
                path=str(clip_path),
            )
        )
    manifest = AudioManifest(coverage=storage.coverage, post_id=storage.post_id, clips=clips)
    storage.save(manifest)
    return manifest


def _ffmpeg_concat(clip_paths: list[Path], out: Path, list_path: Path) -> None:
    list_path.write_text("".join(f"file '{p.resolve()}'\n" for p in clip_paths))
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), str(out)],
        check=True,
        capture_output=True,
    )


def run_concat(storage: Storage, group: int | None = None) -> list[Path]:
    """Join clips into one mp3, or into one file per `group` consecutive replies
    (e.g. group=25 -> output_seq_0000_to_0024.mp3) for easier navigation."""
    manifest = storage.load_manifest()
    ordered = sorted(manifest.clips, key=lambda c: (c.seq, c.chunk_index))

    if group is None:
        _ffmpeg_concat([Path(c.path) for c in ordered], storage.output_path, storage.dir / "_concat.txt")
        return [storage.output_path]

    buckets: dict[int, list] = {}
    for clip in ordered:
        buckets.setdefault(clip.seq // group, []).append(clip)

    outputs = []
    for _, clips in sorted(buckets.items()):
        out = storage.dir / f"output_seq_{clips[0].seq:04d}_to_{clips[-1].seq:04d}.mp3"
        _ffmpeg_concat([Path(c.path) for c in clips], out, out.with_suffix(".concat.txt"))
        outputs.append(out)
    return outputs
