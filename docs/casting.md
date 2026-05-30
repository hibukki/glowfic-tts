# Casting characters to voices

How to give each glowfic character a voice that fits. This is the **process**
(no spoilers); the per-post casting sheet — the info you draw on to choose
voices — is a throwaway preview at `data/{post_id}/casting-preview.md`
(regenerated every run, gitignored). The decisions themselves live in code:
gender in [`characters.py`](../src/glowfic_tts/characters.py), voices in
`data/{post_id}/voices.toml`.

## Signals we use

1. **Centrality** — how much you'll *hear* a character. `cast` ranks speakers by
   word count (and tag count). Spend the best voices on the biggest roles.
2. **The art** — glowfic icons usually reveal gender, age, and vibe. The preview
   shows each character's art inline.
3. **The opening line** — tone/register (playful, regal, stern…).

## Principles (learned so far)

- **Gender match beats voice tier.** A gender-right Enhanced voice is better than
  a gender-wrong Premium one — so autocast **refuses to guess**: a character with
  no gender in `characters.py` fails the build with a worklist, rather than risk a
  male voice on a woman.
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

This writes `data/{post_id}/casting-preview.md` — characters most-central first,
each with its **art previewed inline** (icons downloaded to `data/{post_id}/icons/`),
the opening line, the gender on file, and the auto-assigned voice.

1. For any character shown as `gender: UNKNOWN`, use its art + opening line to
   decide, then add it to `CHARACTERS` in
   [`characters.py`](../src/glowfic_tts/characters.py) (`M`/`F`, or `N` for
   narration/settings). Autocast won't build until every character has one.
2. Build with `glowfic-tts all <post_id> --chapters`: autocast picks a
   gender-matched voice (Premium to the most central). Override any in
   `data/{post_id}/voices.toml`; or build before filling genders with
   `--dangerously-naive-autocast`.

## Voice facts

- macOS `say` **requires Enhanced/Premium English voices** (standard ones are too
  robotic); install via System Settings → Accessibility → Spoken Content. The
  catalog, accents, and curated genders are in
  [`voices.py`](../src/glowfic_tts/voices.py).
- `say -v '?'` does **not** expose gender (we keep a curated map); the language
  code gives the accent.
- To debug a specific tag's audio, browse `data/{post}/{coverage}/by_tag/`
  (`tag_00111_part00.wav`); clips themselves live in the shared `data/{post}/audio/`.
