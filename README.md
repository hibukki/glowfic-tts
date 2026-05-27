# glowfic-tts

Turn a [glowfic](https://glowfic.com) post into a multi-voice audiobook — each
character gets its own voice.

- Design & rationale: [PLAN.md](PLAN.md)
- Picking voices for a post: [docs/casting.md](docs/casting.md)

## Setup

```bash
uv sync
```

## Use

```bash
uv run glowfic-tts cast <post_id> --write    # who's in it + start picking voices
uv run glowfic-tts all  <post_id> --chapters # build the audiobook
```

Each command prints what it produced. `glowfic-tts -h` lists every step and flag
(`--limit`, `--provider gemini`, `--group`, …). macOS `say` (the default) needs
Enhanced/Premium voices and prints install steps if they're missing.

## Dev

```bash
uv run pytest        # offline; uses captured API fixtures
```

Be gentle with glowfic.com: `fetch` is sequential, rate-limited, and caches every
response, so reruns never re-hit the site.
