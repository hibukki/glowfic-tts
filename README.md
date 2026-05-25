# glowfic-tts

Turn a [glowfic](https://glowfic.com) post into a multi-voice audiobook. Each
character gets its own voice. Built as a chain of self-contained steps; the
design and rationale (incl. a Codex review) live in [PLAN.md](PLAN.md).

## Quickstart

```bash
# Free/offline render via macOS `say` (great for iterating):
uv run glowfic-tts all 7508 --limit 25

# Full render via Gemini TTS (needs $GEMINI_API_KEY):
uv run glowfic-tts all 7508 --provider gemini

# Split into one file per 25 replies (easier to navigate):
uv run glowfic-tts all 7508 --limit 100 --group 25
```

Output lands in `data/{post_id}/{coverage}/` (one `output.mp3`, or
`output_seq_*.mp3` files with `--group`). Drop `--limit` for the whole post.

The `say` provider **requires Enhanced/Premium English voices** (the standard
ones are too robotic); it crashes with install instructions if they're missing.
Install them once via System Settings → Accessibility → Spoken Content →
System Voice → Manage Voices, then re-run `voices`.

## Pipeline

Each step reads the previous artifact and writes the next; rerun any step freely.

| Step | Writes |
|---|---|
| `fetch` | `01_raw/` — cached glowfic API responses (the only network step) |
| `assemble` | `02_story.json` — ordered segments (opening post + replies) |
| `extract` | `03_script.json` — HTML→rich text, chunked under the TTS limit |
| `voices` | `voices.toml` — character → voice, **hand-editable** |
| `bind` | `04_lines.json` — resolved `voice: text` lines |
| `tts` | `05_audio/` — one clip per line, cached by synthesis fingerprint |
| `concat` | `output.mp3` |

Stages are pure functions over [pydantic models](src/glowfic_tts/models.py); the
[orchestrator](src/glowfic_tts/pipeline.py) owns all disk IO and the fetch/TTS
cache loops.

## Editing voices

After `voices` (or any `all` run), edit `data/{post_id}/voices.toml` to taste,
then rerun `bind` + `tts` + `concat`. The voice list per provider is in
[voices.py](src/glowfic_tts/voices.py) (Gemini voices + sample macOS `say` voices).

## Dev

```bash
uv run pytest        # offline; uses captured API fixtures in tests/fixtures/
```

Be gentle with glowfic.com: `fetch` is sequential with a delay and caches every
response, so reruns never re-hit the site.
