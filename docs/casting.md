# Casting characters to voices

How to give each glowfic character a voice that fits. This is the **process**
(no spoilers); the per-character decisions for a specific post live in
`data/{post_id}/casting.md` (gitignored, so spoilers stay off the repo).

## Signals we use

1. **Centrality** — how much you'll *hear* a character. `cast` ranks speakers by
   word count (and tag count). Spend the best voices on the biggest roles.
2. **The art** — glowfic icons usually reveal gender, age, and vibe. Open the
   `icon:` URL from the casting sheet and look.
3. **The opening line** — tone/register (playful, regal, stern…).

## Principles (learned so far)

- **Gender match beats voice tier.** A gender-right Enhanced voice is better than
  a gender-wrong Premium one. (We once auto-assigned a male voice to a woman —
  don't.)
- **Premium to the most central**, Enhanced to the long tail. `make_voicemap`
  does this automatically: it casts most-central-first from a Premium-first pool.
- **Distinct accents/voices** for characters who interact, so they're easy to tell
  apart (accent comes free from the voice's language code).
- **Institutions/places** (e.g. a nation or order acting as narrator) → a neutral
  narrator voice, gender irrelevant.
- **macOS `say` can't act.** It reads words clearly but flat; comedic/manic/childlike
  delivery needs **Gemini TTS** (style prompts) — the `title`/`style_prompt` fields
  exist for that. See voice facts in [`voices.py`](../src/glowfic_tts/voices.py).

## Workflow

```bash
uv run glowfic-tts cast <post_id>
```

This writes `data/{post_id}/casting.md` — characters most-central first, each with
its **art previewed inline** (icons are downloaded to `data/{post_id}/icons/`), the
opening line, current voice, and the available voices at the bottom.

1. Open it in a Markdown previewer and, for the central characters, fill each
   `art/gender:` line (gender + a one-line description). These notes are
   **preserved** when you re-run `cast`.
2. Set voices in `data/{post_id}/voices.toml` (gender-appropriate; Premium for the
   most central), then build with `glowfic-tts all <post_id> --chapters`.

## Voice facts

- macOS `say` **requires Enhanced/Premium English voices** (standard ones are too
  robotic); install via System Settings → Accessibility → Spoken Content. The
  catalog, accents, and curated genders are in
  [`voices.py`](../src/glowfic_tts/voices.py).
- `say -v '?'` does **not** expose gender (we keep a curated map); the language
  code gives the accent.
- To debug a specific tag's audio, browse `data/{post}/{coverage}/by_tag/`
  (`tag_00111_part00.wav`); clips themselves live in the shared `data/{post}/audio/`.
