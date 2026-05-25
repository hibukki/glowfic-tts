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
from .voices import GEMINI_TTS_MODEL

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
    voicemap = stages.make_voicemap(storage.load_script(), existing=storage.load_voicemap())
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


def run_tts(storage: Storage, provider: str = "say", api_key: str | None = None) -> AudioManifest:
    synth, model = _provider(provider, api_key)
    lines: Lines = storage.load_lines()
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


def run_concat(storage: Storage) -> Path:
    manifest = storage.load_manifest()
    ordered = sorted(manifest.clips, key=lambda c: (c.seq, c.chunk_index))
    listing = "".join(f"file '{Path(c.path).resolve()}'\n" for c in ordered)
    list_path = storage.dir / "_concat.txt"
    list_path.write_text(listing)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), str(storage.output_path)],
        check=True,
        capture_output=True,
    )
    return storage.output_path
