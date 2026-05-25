# glowfic → audio pipeline — plan

Turn a glowfic post (e.g. https://glowfic.com/posts/7508) into a multi-voice audiobook.
This is primarily a **define-nice-APIs** project; TTS just happens to be the last step.

> Revised after a Codex adversarial review (see "Review fixes" markers).

## Key discovery: there is a clean JSON API (no HTML scraping)

- `GET /api/v1/posts/{id}` → post metadata + opening post `content` (HTML), `character`, `icon`, `authors`, `num_replies`.
- `GET /api/v1/posts/{id}/replies?per_page=N&page=M` → paginated replies. Each reply:
  `{ id, content (HTML), character:{id,name,screenname}, icon:{id,url,keyword}, user:{id,username} }`

Post 7508 has **2064 replies**. Each reply is one character's POV → **reply maps to one voice**. That alone yields a natural multi-voice reading; no LLM needed.

## Design principles

1. **Pure transform stages over pydantic objects; the orchestrator owns ALL disk IO.**
   `assemble(raw) -> Story`, `extract(story) -> Script`, `bind(script, vm) -> Lines` are pure and disk-ignorant.
2. **Network/TTS stages are orchestrated loops, not pure functions** *(Review fix #4 — IO ownership)*.
   The fetch adapter and the TTS adapter only do network → object/bytes. The **orchestrator** owns the loop: check cache file → call adapter only on miss → write artifact → validate. No hidden caches inside adapters. This keeps a single IO owner while staying polite and resumable.
3. **Multi-provider voice config from day 1.** A `Voice` carries per-provider settings (`gemini`, `elevenlabs`, …) so we can switch/add providers without reshaping data.
4. **The text schema must not assume away features.** Emphasis (`<em>`/`<i>`), strong, paragraph breaks are preserved as structured rich text even though the first TTS pass renders plain text.
5. **Speaker travels with the text** *(Review fix #1)*. Every `Chunk` carries its own `voice_key`, so binding never has to guess from `seq`.
6. **Audio is cached by a full synthesis fingerprint** *(Review fix #2)*, not by text alone: hash of `{provider, model, voice config, normalized text, output format, tts params}`. Change a voice → cache miss → re-synth.
7. **Slice runs are isolated from full runs** *(Review fix #3)*. Artifacts live under a **coverage** sub-path and every artifact records its coverage; the orchestrator refuses to feed a slice into a full run.
8. **Web-scraping hygiene:** one network step, sequential, delay between requests, identifying User-Agent, every raw response cached. Steps 2–6 run fully offline and are infinitely re-runnable.

## Tech

- Python + `uv`. `pydantic` v2 for the schema. `httpx` for fetch. `selectolax`/`lxml` for HTML→rich-text. `ffmpeg` (system) for concat. Gemini TTS via `google-genai`.
- Single package `glowfic_tts/`. CLI subcommands: `glowfic-tts fetch|assemble|extract|voices|tts|concat|all <post_id> [--limit N]`.

## Coverage & artifacts on disk

`coverage` is `full` or `limit_{N}`. Slice and full runs never share files.

```
data/{post_id}/{coverage}/
  01_raw/
    post.json
    replies/page_0001.json …
  02_story.json
  03_script.json
  04_lines.json
  05_audio/<synthesis_key>.wav …     # keyed by fingerprint, not seq
  05_manifest.json
  output.mp3
data/{post_id}/voices.toml           # shared across coverages, hand-editable
```

## Shared schema (sketch — `glowfic_tts/models.py`)

```python
class Coverage(BaseModel):            # Review fix #3 — stamped on every artifact
    kind: Literal["full", "limit"]
    limit: int | None = None          # set when kind == "limit"
    def slug(self) -> str: ...        # "full" or "limit_25"

# --- rich text: preserves emphasis without forcing TTS to use it ---
class TextRun(BaseModel):
    text: str
    emphasis: bool = False            # <em>/<i>
    strong: bool = False              # <strong>/<b>
class RichText(BaseModel):
    runs: list[TextRun]
    def plain(self) -> str: ...       # first TTS pass uses this

# --- who is speaking / which voice key ---
class Speaker(BaseModel):
    character_id: int | None
    character_name: str | None
    screenname: str | None
    username: str                     # author, always present
    @property
    def voice_key(self) -> str: ...   # stable key into the voice map

# --- canonical story (step 2) ---
class Segment(BaseModel):
    seq: int                          # 0 = opening post, 1.. = replies in order
    reply_id: int | None
    speaker: Speaker
    icon_keyword: str | None
    content_html: str                 # kept for traceability
class Story(BaseModel):
    coverage: Coverage
    post_id: int
    subject: str
    authors: list[Speaker]
    segments: list[Segment]

# --- parsed + chunked script (step 3) ---
class Chunk(BaseModel):
    seq: int
    chunk_index: int
    voice_key: str                    # Review fix #1 — speaker travels with text
    rich: RichText                    # structured; .plain() for now
class Script(BaseModel):
    coverage: Coverage
    post_id: int
    subject: str
    chunks: list[Chunk]
    speakers: dict[str, Speaker]      # voice_key -> Speaker (for voices.toml generation)

# --- multi-provider voice config (step 4) ---
class GeminiVoice(BaseModel):
    voice_name: str                   # e.g. "Kore", "Puck" — verify list in docs
    style_prompt: str | None = None
class ElevenLabsVoice(BaseModel):
    voice_id: str
class Voice(BaseModel):
    gemini: GeminiVoice | None = None
    elevenlabs: ElevenLabsVoice | None = None
class VoiceMap(BaseModel):
    voices: dict[str, Voice]          # voice_key -> Voice (voices.toml)

# --- bound lines (step 4b) ---
class Line(BaseModel):
    seq: int
    chunk_index: int
    voice_key: str
    voice: Voice                      # resolved from VoiceMap
    text: str                         # rich.plain() for now
class Lines(BaseModel):
    coverage: Coverage
    post_id: int
    lines: list[Line]

# --- audio (step 5) ---
class SynthSpec(BaseModel):           # Review fix #2 — the full fingerprint
    provider: str
    model: str
    voice: Voice
    output_format: str
    params: dict[str, str | float | int] = {}
    text: str
    def key(self) -> str: ...         # stable hash over all fields → cache filename
class AudioClip(BaseModel):
    seq: int
    chunk_index: int
    synthesis_key: str
    spec: SynthSpec                   # resolved config stored, not just provider
    path: str
class AudioManifest(BaseModel):
    coverage: Coverage
    post_id: int
    clips: list[AudioClip]
```

## Stage contracts

| Step | Kind | Signature / loop | IO owner |
|---|---|---|---|
| 1 fetch | orchestrated loop | adapter: `get_post(id)`, `get_replies_page(id, page)` → parsed objects. Orchestrator: per-page cache check → write `01_raw/` → assemble `RawPost` | orchestrator |
| 2 assemble | pure | `assemble(raw: RawPost) -> Story` | orchestrator |
| 3 extract | pure | `extract(story: Story) -> Script` (HTML→RichText, chunking, carries `voice_key`) | orchestrator |
| 4a voices | pure | `make_voicemap(script, existing) -> VoiceMap` (auto-assign Gemini voices round-robin, merge user edits) | orchestrator |
| 4b bind | pure | `bind(script: Script, vm: VoiceMap) -> Lines` | orchestrator |
| 5 tts | orchestrated loop | adapter: `synthesize(spec: SynthSpec) -> bytes`. Orchestrator: build `SynthSpec` per line → cache check by `spec.key()` → write `.wav` → `AudioManifest` | orchestrator |
| 6 concat | pure-ish | `concat_plan(manifest) -> list[Path]`; orchestrator runs ffmpeg | orchestrator |

The orchestrator owns a single `load(stage, coverage) ⇄ save(stage, coverage, obj)` mapping and refuses to load an artifact whose `coverage` mismatches the requested run.

## Testing — before any paid TTS *(Review fix #5)*

Blocking, fixture-based, no happy-path-only:
- **Fixture:** capture one real `post.json` + one real `replies` page from the API; commit as test data.
- Validate the live response parses into the schema (catches API drift).
- Assert ordering: opening post is `seq 0`, replies follow API order, no gaps across page boundaries.
- `--limit` isolation: a `limit_25` run never reads/writes `full` paths.
- Chunk→speaker preservation: every `Chunk.voice_key` matches its source `Segment.speaker.voice_key`.
- Cache-key correctness: changing voice/provider/format/params changes `SynthSpec.key()`; identical inputs reuse the clip.
- `concat` on a few synthetic tiny WAVs (no provider calls).
- TTS adapter is mockable so the whole pipeline is testable offline.

## Open items to verify during implementation (official docs, link in code)

- Gemini TTS: model id (`gemini-2.5-flash-preview-tts`?), prebuilt voice-name list, input length limit (drives chunk size), output format. Verify via official docs / context7.
- Glowfic API: max `per_page`, rate-limit headers, opening-post vs replies call shape, page-boundary ordering. Discover politely in step 1 / fixture.
- HTML quirks in `content`: images, links, blockquotes, nested formatting — decide rendering per element in `extract`.

## First milestone (agreed)

Full pipeline + the tests above, run on a **`--limit ~25`** slice of post 7508 → `output.mp3`, listen, then scale up. Commit per step (per global CLAUDE.md).
