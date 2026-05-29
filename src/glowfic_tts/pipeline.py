"""Orchestrator: owns the cache loops, all disk IO, and stage sequencing.

Each `run_*` loads its inputs via Storage, calls a pure stage (or a network
adapter), and saves the result. Fetch and TTS are cache loops: hit the network
only on a miss, write the artifact, move on (Review fix #4).
"""

from __future__ import annotations

import functools
import hashlib
import os
import re
import subprocess
import wave
from collections import Counter
from contextlib import nullcontext
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from . import stages
from .api import DEFAULT_USER_AGENT, GlowficClient, RawPost
from .models import AudioClip, AudioManifest, Lines, SynthSpec
from .storage import Storage
from .tts import Synth, make_gemini_synth, synth_say
from .voices import (
    GEMINI_SAMPLE_RATE,
    GEMINI_TTS_MODEL,
    MAC_SAY_VOICES,
    SAY_INSTALL_HELP,
    SAY_SAMPLE_RATE,
    installed_quality_say_voices,
    installed_quality_say_voices_meta,
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


def ensure_casting_inputs(storage: Storage, client: GlowficClient | None = None) -> None:
    """Run every step `cast` reads from (fetch -> assemble -> extract -> voices).

    Each step owns its own caching/recompute (fetch hits the network only on a
    miss; the rest are sub-second pure transforms), so this is cheap on re-runs
    and `cast` never has to know where intermediate artifacts live. Pass `client`
    to reuse/inject one (tests); otherwise we open and close our own.
    """
    with (nullcontext(client) if client else GlowficClient()) as c:
        run_fetch(storage, c, storage.post_id, storage.coverage.limit)
    run_assemble(storage)
    run_extract(storage)
    run_voices(storage)


def casting_sheet(storage: Storage) -> list[dict]:
    """Per character: centrality (tags spoken + word count), opening line, and
    current say voice — sorted most-central first, to cast (and budget Premium
    voices) by importance."""
    script = storage.load_script()
    voicemap = storage.load_voicemap()
    first_line: dict[str, str] = {}
    tags: dict[str, set[int]] = {}
    words: Counter[str] = Counter()
    for chunk in script.chunks:
        text = chunk.rich.plain()
        first_line.setdefault(chunk.voice_key, text)
        tags.setdefault(chunk.voice_key, set()).add(chunk.seq)
        words[chunk.voice_key] += len(text.split())

    rows = []
    for voice_key, text in first_line.items():
        speaker = script.speakers[voice_key]
        entry = voicemap.voices.get(voice_key) if voicemap else None
        rows.append({
            "character": voice_key,
            "screenname": speaker.screenname,
            "tags": len(tags[voice_key]),
            "words": words[voice_key],
            "current_say": entry.say.voice_name if (entry and entry.say) else None,
            "first_line": " ".join(text.split())[:160],
        })
    rows.sort(key=lambda r: r["words"], reverse=True)
    return rows


def _icon_urls_by_voice_key(storage: Storage) -> dict[str, str]:
    raw = storage.load_raw()
    urls: dict[str, str] = {}

    def key(character, character_name, username) -> str:
        name = (character.name if character else None) or character_name
        screen = character.screenname if character else None
        return name or screen or f"@{username}"

    if raw.post.character and raw.post.icon and raw.post.icon.url:
        urls.setdefault(key(raw.post.character, None, raw.post.authors[0].username), raw.post.icon.url)
    for reply in raw.replies:
        if reply.icon and reply.icon.url:
            urls.setdefault(key(reply.character, reply.character_name, reply.user.username), reply.icon.url)
    return urls


def _download_icons(storage: Storage, urls: dict[str, str]) -> dict[str, str]:
    """Download each character's icon into data/{post}/icons/ (cached). Returns
    paths relative to casting.md so the doc can preview them inline."""
    icons_dir = storage.base / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)
    rel: dict[str, str] = {}
    with httpx.Client(headers={"User-Agent": DEFAULT_USER_AGENT}, timeout=30) as client:
        for key, url in urls.items():
            ext = os.path.splitext(url.split("?")[0])[1] or ".png"
            slug = re.sub(r"[^\w-]+", "_", key).strip("_")
            # hash the key so distinct characters never collide on a shared slug
            digest = hashlib.sha1(key.encode()).hexdigest()[:8]
            path = icons_dir / f"{slug}_{digest}{ext}"
            if not path.exists():
                response = client.get(url)
                response.raise_for_status()
                path.write_bytes(response.content)
            rel[key] = f"icons/{path.name}"
    return rel


def write_casting_doc(storage: Storage) -> Path:
    """Write a per-post casting sheet to data/{post}/casting.md (gitignored, so
    spoilers stay off the repo). Everything for casting lives here: centrality,
    the downloaded art (previewed inline), opening lines, current voice, and the
    available voices. Hand-written art/gender notes are preserved on re-runs."""
    rows = casting_sheet(storage)
    icons = _download_icons(storage, _icon_urls_by_voice_key(storage))
    openings: dict[str, str] = {}
    for chunk in storage.load_script().chunks:
        openings.setdefault(chunk.voice_key, " ".join(chunk.rich.plain().split())[:400])

    out = storage.base / "casting.md"
    prior_art = _existing_art_notes(out)

    lines = [
        f"# Casting — post {storage.post_id} (SPOILERS)",
        "",
        "Per character below: fill in `art/gender` from the previewed icon, then set "
        "voices in `voices.toml`. Available voices are listed at the bottom.",
        "",
    ]
    for row in rows:
        screen = f" ~{row['screenname']}" if row["screenname"] else ""
        heading = f"{row['character']}{screen}"
        icon = icons.get(row["character"])
        lines += [
            f"## {heading}",
            f"![]({icon})" if icon else "_(no icon)_",
            f"- central: {row['tags']} tags, {row['words']} words",
            f"- voice: {row['current_say']}",
            f"- art/gender: {prior_art.get(heading, '_(fill in)_')}",
            f"- opening: {openings.get(row['character'], '')}",
            "",
        ]
    lines += ["## Available voices (name | accent | gender)", ""]
    lines += [f"- {v['name']} | {v['accent']} | {v['gender']}" for v in installed_quality_say_voices_meta()]
    out.write_text("\n".join(lines) + "\n")
    return out


def _existing_art_notes(casting_md: Path) -> dict[str, str]:
    if not casting_md.exists():
        return {}
    notes: dict[str, str] = {}
    heading = None
    for line in casting_md.read_text().splitlines():
        if line.startswith("## "):
            heading = line[3:].strip()
        elif line.startswith("- art/gender:") and heading:
            value = line.split(":", 1)[1].strip()
            if value and value != "_(fill in)_":
                notes[heading] = value
    return notes


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


def run_tts(
    storage: Storage, provider: str = "say", api_key: str | None = None, workers: int | None = None
) -> AudioManifest:
    synth, model = _provider(provider, api_key)
    lines: Lines = storage.load_lines()
    if provider == "say":
        _require_quality_say_voices(lines)
    storage.audio_dir.mkdir(parents=True, exist_ok=True)
    sample_rate = SAY_SAMPLE_RATE if provider == "say" else GEMINI_SAMPLE_RATE

    clips = []
    for line in lines.lines:
        spec = SynthSpec(
            provider=provider, model=model, voice=line.voice,
            output_format="wav", text=line.text, params={"sample_rate": sample_rate},
        )
        clips.append(
            AudioClip(
                seq=line.seq, chunk_index=line.chunk_index, synthesis_key=spec.key(),
                spec=spec, path=str(storage.audio_dir / f"{spec.key()}.wav"),
            )
        )

    # Synthesize only cache misses, deduped by path, in parallel.
    todo = {clip.path: clip.spec for clip in clips if not Path(clip.path).exists()}
    if todo:
        if workers is None:
            workers = min(8, os.cpu_count() or 4) if provider == "say" else 3
        with ThreadPoolExecutor(max_workers=workers) as pool:
            # list() so any synth exception surfaces instead of being swallowed.
            list(pool.map(lambda item: Path(item[0]).write_bytes(synth(item[1])), todo.items()))

    _link_clips_by_tag(storage, clips)
    manifest = AudioManifest(coverage=storage.coverage, post_id=storage.post_id, clips=clips)
    storage.save(manifest)
    return manifest


def _link_clips_by_tag(storage: Storage, clips: list[AudioClip]) -> None:
    """Symlink each content-hashed clip (in the shared audio cache) under this
    coverage's by_tag/tag_00111_part00.wav, so a specific tag is easy to find."""
    by_tag = storage.dir / "by_tag"
    by_tag.mkdir(parents=True, exist_ok=True)
    for stale in by_tag.glob("*.wav"):
        stale.unlink()
    for clip in clips:
        label = "intro" if clip.chunk_index < 0 else f"part{clip.chunk_index:02d}"
        link = by_tag / f"tag_{clip.seq:05d}_{label}.wav"
        link.symlink_to(os.path.relpath(clip.path, by_tag))


@functools.cache
def _aac_encoder() -> str:
    """Apple's AudioToolbox AAC if available (best for Apple Books), else portable
    native aac (Linux/CI have no aac_at)."""
    encoders = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    return "aac_at" if "aac_at" in encoders else "aac"


def _wav_frames_rate(path: Path) -> tuple[int, int]:
    with wave.open(str(path), "rb") as w:
        return w.getnframes(), w.getframerate()


def _ffmeta_escape(text: str) -> str:
    for ch in ("\\", "=", ";", "#"):
        text = text.replace(ch, "\\" + ch)
    return text.replace("\n", " ")


def run_chapters(storage: Storage) -> Path:
    """Build one `.m4b` audiobook with a chapter per glowfic tag (reply), titled
    `0012 Character: first words…`. Apple Books remembers position + lists chapters."""
    manifest = storage.load_manifest()
    lines = storage.load_lines()
    ordered = sorted(manifest.clips, key=lambda c: (c.seq, c.chunk_index))

    title_for: dict[int, str] = {}
    for line in lines.lines:
        if line.seq not in title_for:
            words = " ".join(line.text.split())[:48]
            title_for[line.seq] = f"{line.seq:04d} {line.voice_key}: {words}"

    # Chapter times from cumulative frame counts (not summed rounded ms), so
    # boundaries stay sample-exact and don't drift over a long book.
    _, rate = _wav_frames_rate(Path(ordered[0].path))
    starts: dict[int, int] = {}
    ends: dict[int, int] = {}
    frames = 0
    for clip in ordered:
        starts.setdefault(clip.seq, round(1000 * frames / rate))
        frames += _wav_frames_rate(Path(clip.path))[0]
        ends[clip.seq] = round(1000 * frames / rate)

    meta = [";FFMETADATA1"]
    for seq in sorted(starts):
        meta += [
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={starts[seq]}",
            f"END={ends[seq]}",
            f"title={_ffmeta_escape(title_for.get(seq, str(seq)))}",
        ]

    meta_path = storage.dir / "_chapters.txt"
    meta_path.write_text("\n".join(meta) + "\n")
    combined = _concat_to_wav([Path(c.path) for c in ordered], storage.dir / "_combined.wav")
    out = storage.dir / "output.m4b"
    # Apple's AudioToolbox AAC at a standard 44100 Hz + faststart — most compatible
    # with Apple Books (ffmpeg's native aac at 22050 stuttered there).
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(combined), "-i", str(meta_path),
         "-map", "0:a", "-map_metadata", "1", "-map_chapters", "1",
         "-ar", "44100", "-c:a", _aac_encoder(), "-b:a", "64k", "-movflags", "+faststart", str(out)],
        check=True,
        capture_output=True,
    )
    combined.unlink(missing_ok=True)
    return out


def _concat_to_wav(clip_paths: list[Path], combined: Path) -> Path:
    """Join clips into one WAV by copying raw PCM frames (via the `wave` module),
    not by stitching WAV containers in ffmpeg. `readframes` returns exactly the
    audio samples regardless of any header quirks, so the result is a single clean
    continuous stream — no inter-clip seams that a player could stumble on."""
    with wave.open(str(clip_paths[0]), "rb") as first:
        params = first.getparams()
    fmt = (params.framerate, params.nchannels, params.sampwidth)
    with wave.open(str(combined), "wb") as out:
        out.setparams(params)
        for path in clip_paths:
            with wave.open(str(path), "rb") as clip:
                if (clip.getframerate(), clip.getnchannels(), clip.getsampwidth()) != fmt:
                    raise ValueError(f"{path} format {clip.getparams()} != {fmt}; can't concat")
                out.writeframes(clip.readframes(clip.getnframes()))
    return combined


def _ffmpeg_concat(clip_paths: list[Path], out: Path) -> None:
    combined = _concat_to_wav(clip_paths, out.with_suffix(".combined.wav"))
    subprocess.run(["ffmpeg", "-y", "-i", str(combined), str(out)], check=True, capture_output=True)
    combined.unlink(missing_ok=True)


def run_concat(storage: Storage, group: int | None = None) -> list[Path]:
    """Join clips into one mp3, or into one file per `group` consecutive replies
    (e.g. group=25 -> output_seq_0000_to_0024.mp3) for easier navigation."""
    manifest = storage.load_manifest()
    ordered = sorted(manifest.clips, key=lambda c: (c.seq, c.chunk_index))

    if group is None:
        _ffmpeg_concat([Path(c.path) for c in ordered], storage.output_path)
        return [storage.output_path]

    buckets: dict[int, list] = {}
    for clip in ordered:
        buckets.setdefault(clip.seq // group, []).append(clip)

    outputs = []
    for _, clips in sorted(buckets.items()):
        out = storage.dir / f"output_seq_{clips[0].seq:04d}_to_{clips[-1].seq:04d}.mp3"
        _ffmpeg_concat([Path(c.path) for c in clips], out)
        outputs.append(out)
    return outputs
