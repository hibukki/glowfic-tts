# glowfic-tts

Turn a [glowfic](https://glowfic.com) post into a multi-voice audiobook — each
character gets its own voice. Design and rationale (incl. Codex reviews) live in
[PLAN.md](PLAN.md); the voice-casting method in [docs/casting.md](docs/casting.md).

## Quickstart

```bash
# 1. See who's in the story and start picking voices (writes an editable sheet):
uv run glowfic-tts cast <post_id> --write        # -> data/{post_id}/casting.md

# 2. Make the audiobook — one chaptered .m4b (open in Apple Books):
uv run glowfic-tts all <post_id> --chapters
```

Defaults to free/offline macOS `say`; add `--provider gemini` (needs
`$GEMINI_API_KEY`) for cloud TTS. `--limit N` does a slice first; `--group N`
emits one file per N tags instead of a single chaptered file. Output lands in
`data/{post_id}/{coverage}/` (`output.m4b`, or `output_seq_*.mp3` with `--group`).

## Choosing voices

`cast` ranks characters by how much you'll hear them and lists the installed
voices; you note the art and set `data/{post_id}/voices.toml`. The full method,
principles, and `say` voice requirements are in [docs/casting.md](docs/casting.md).

## Pipeline

Each step reads the previous artifact and writes the next; rerun any step freely.
`cast` is a helper (not in the chain) for the voice-picking above.

| Step | Writes |
|---|---|
| `fetch` | `01_raw/` — cached glowfic API responses (the only network step) |
| `assemble` | `02_story.json` — ordered segments (opening post + replies) |
| `extract` | `03_script.json` — HTML→rich text, chunked under the TTS limit |
| `voices` | `voices.toml` — character → voice, **hand-editable** |
| `bind` | `04_lines.json` — resolved `voice: text` lines |
| `tts` | clips in shared `audio/` (cached by synthesis fingerprint, content-addressed across coverages) |
| `concat` | `output.mp3`, or `output.m4b` with `--chapters` |

Stages are pure functions over [pydantic models](src/glowfic_tts/models.py); the
[orchestrator](src/glowfic_tts/pipeline.py) owns all disk IO and the fetch/TTS
cache loops.

## Dev

```bash
uv run pytest        # offline; uses captured API fixtures in tests/fixtures/
```

Be gentle with glowfic.com: `fetch` is sequential with a delay and caches every
response, so reruns never re-hit the site.
