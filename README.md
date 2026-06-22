# glowfic-tts

Turn a [glowfic](https://glowfic.com) post into a multi-voice audiobook — each
character gets its own voice.

- Picking voices for a post: [docs/casting.md](docs/casting.md)
- Listening on Android (export + Syncthing): [docs/android-sync.md](docs/android-sync.md)

## Setup

```bash
uv sync
```

## Use

```bash
uv run glowfic-tts cast   <post_id>            # who's in it; pick voices
uv run glowfic-tts all    <post_id> --chapters # build the audiobook
uv run glowfic-tts export <post_id> --to <dir> # publish .m4b to <dir>/<Book Title>/
```

`glowfic-tts -h` lists every step and flag. macOS `say` (the default voice engine)
needs a one-time setup — see [docs/casting.md](docs/casting.md).

## Dev

```bash
uv run pytest
```
