# Listening on Android (Smart Audiobook Player)

Goal: build a book on the Mac and have it appear on the phone under
`/Audiobooks/<Book Title>/`, where **Smart Audiobook Player** (SABP) treats each
subfolder as one book.

Two pieces: **export** (this tool drops a clean book folder onto disk) and
**sync** (Syncthing mirrors that folder to the phone).

## 1. Export

`export` copies the chaptered `output.m4b` into `<dir>/<Book Title>/`, named from
the post subject, plus the post's icon as `cover.<ext>` (SABP shows it as art).
Point `<dir>` at the folder Syncthing watches (see below):

```bash
export GLOWFIC_AUDIOBOOKS_DIR=~/GlowficAudiobooks      # set once (e.g. in ~/.zshrc)
glowfic-tts all <post_id> --chapters                   # build + auto-export
# or, after a build:  glowfic-tts export <post_id>
```

A single `.m4b` carries its chapters (one per glowfic reply) inside the file, so
SABP shows the chapter list and remembers your position.

## 2. Syncthing (Mac ↔ Android)

Direct device-to-device sync — no cloud, no on-demand streaming, real files land
in the phone's `/Audiobooks/`. (The plain Google Drive app *streams* files and
won't mirror them into a local folder SABP can read, which is why we don't use it.)

**Mac:**

```bash
brew install syncthing
brew services start syncthing       # runs at login; GUI at http://127.0.0.1:8384
```

In the GUI: **Add Folder** → Folder Path = your `GLOWFIC_AUDIOBOOKS_DIR`
(`~/GlowficAudiobooks`), give it a memorable Folder ID like `audiobooks`. Under
that folder's **Sharing** tab you'll tick the phone once it's paired (next step).

**Android:** install **Syncthing** (F-Droid or Play Store).

1. Pair the devices: on the Mac GUI, **Actions → Show ID** (a QR code). In the
   Android app, **+ → Add Device → scan QR**. Accept the pairing prompt that pops
   up back on the Mac.
2. Android will offer the shared `audiobooks` folder — accept it and set its
   folder path to `/storage/emulated/0/Audiobooks` (this *is* the `/Audiobooks/`
   SABP scans).
3. Set folder type **Receive Only** on the phone and **Send Only** on the Mac, so
   the Mac stays the source of truth and the phone never pushes edits back.

That's it — `glowfic-tts all <id> --chapters` now puts a new book on the phone a
minute or two later (instant on the same Wi-Fi). Open SABP and it's there.
