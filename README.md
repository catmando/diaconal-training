# Hierarchical Divine Liturgy — Deacon Training Video

A training video for **deacons**, assembled from 37 clips filmed at a
hierarchical Divine Liturgy on **20 June 2026** (OCA, Diocese of New York and
New Jersey). Each clip covers one step of the service; the build overlays
rubric-level explanatory text and writes chapter markers.

This README is a runbook. Following it top to bottom takes a bare machine to a
finished video.

> **Working notes live in [`CLAUDE.md`](CLAUDE.md)** — project state, open
> questions, editorial to-dos, and traps worth knowing before you change
> anything. This file covers setup and rebuild only.

---

## What is and isn't in this repository

Git tracks only what can't be regenerated — the scripts, the edit sheet, and
the notes. That's under 100 KB.

The **37 source clips are 6.8 GB**, far past GitHub's 100 MB per-file limit, so
they're published as assets on the [`raw-footage-v1`][release] release instead.
[`raw_clips.tsv`](raw_clips.tsv) records the size, SHA-256, duration, and codec
of every clip, so a restore can be proven byte-identical rather than assumed.

Everything else — `normalized/`, `master.mp4`, the MKV, the subtitle and chapter
files — is a build product and is rebuilt from those two inputs.

[release]: https://github.com/catmando/diaconal-training/releases/tag/raw-footage-v1

---

## Recovering onto a new machine

**Requirements:** a Mac (Apple Silicon or Intel). The card renderer looks for
macOS system fonts, so this toolchain is macOS-only as written. You need about
**40 GB free** — 6.8 GB of footage, 7.3 GB normalized, and roughly 14 GB of
output.

### 1. Command line tools and Homebrew

```bash
xcode-select --install                     # skip if already present

/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Follow Homebrew's closing instructions to add it to your `PATH` (on Apple
Silicon that's `eval "$(/opt/homebrew/bin/brew shellenv)"`).

### 2. Install the tools

```bash
brew install git gh python
```

Then the one Python package the build needs, **PyYAML**, which reads the edit
sheet:

```bash
pip3 install --break-system-packages pyyaml
```

The `--break-system-packages` flag looks alarming and isn't. Homebrew's Python
is marked "externally managed" under [PEP 668][pep668], so `pip3 install`
refuses by default to protect Homebrew-managed packages. PyYAML is pure Python
with no dependencies, so this is safe; the flag only tells pip you meant it.
Undo any time with `pip3 uninstall pyyaml`.

If you'd rather keep the system Python untouched, a virtualenv works equally
well — just remember to run the build with it:

```bash
python3 -m venv .venv && .venv/bin/pip install pyyaml
.venv/bin/python build.py          # instead of python3 build.py
```

[pep668]: https://peps.python.org/pep-0668/

### 3. Install ffmpeg — from the tap, not the default formula

```bash
brew tap homebrew-ffmpeg/ffmpeg
brew install homebrew-ffmpeg/ffmpeg/ffmpeg
```

**This step matters.** The build needs the `drawtext` filter for title cards and
`libass` for the annotation overlay. The stock `brew install ffmpeg` formula has
shipped without them, which is why this project uses the
`homebrew-ffmpeg/ffmpeg` tap. If cards or annotations come out blank, this is
almost always why. `check_environment.sh` (step 6) tests for exactly this.

### 4. Authenticate with GitHub

```bash
gh auth login
```

### 5. Clone

```bash
git clone https://github.com/catmando/diaconal-training.git
cd diaconal-training
```

### 6. Check the machine before spending hours on it

```bash
./check_environment.sh
```

Verifies the tools, the specific ffmpeg filters and encoders the build uses, a
usable font, GitHub auth, disk space, and how much footage is already present.
Fix anything it marks ✗ before continuing.

### 7. Restore the footage

```bash
./restore_raw_clips.sh
```

Downloads all 37 clips (6.8 GB) into `raw/` and SHA-256 checks every one against
`raw_clips.tsv`. Safe to re-run — valid files are skipped, so an interrupted
download just needs the command again.

```bash
./restore_raw_clips.sh --verify     # check what's on disk, download nothing
```

### 8. Normalize — long, run it overnight

```bash
./normalize_and_join.sh
```

Re-encodes all 37 clips to a common 1920×1080 / 30 fps / AAC format in
`normalized/`, then joins them into `output/master.mp4`. The source clips are
**not uniformly 30 fps** — 25 are 30 fps, six are 29.83, five are 29.75, and one is 120 fps —
so concatenation without this step produces broken timing. That's what this
script exists for.

It re-encodes an hour of 1080p at `-crf 18 -preset slow`, so it's built for an
unattended overnight run. It also resumes: clips already encoded are skipped, so
if it dies partway just run it again.

### 9. Build

```bash
python3 build.py
```

Produces `output/master.mp4`, `output/liturgy_training.mkv` (annotations and
chapters embedded), and the chapter and subtitle sidecar files.

---

## Everyday use

```bash
python3 check_sheet.py           # validate the edit sheet, build nothing
python3 build.py                 # full build (validates first; errors stop it)
python3 build.py --help          # flags AND the full edit-sheet reference
python3 build.py --clip 3        # preview one clip (also 3-5 or 3,7,19)
python3 build.py --clip 3 --draft  # ~4x faster re-encode while checking timings
python3 build.py --clip 3 --play   # open the result in VLC when it succeeds
python3 build.py --clip 3 --timecode --draft   # show ORIGINAL clip times on screen
python3 build.py --subs-only     # regenerate annotations only — fast
python3 build.py --speed 6       # global rate for every speed row
python3 build.py --no-mkv
python3 build.py --youtube       # burn subtitles in; slow, re-encodes
```

Preview mode writes `output/preview.*` and leaves the real outputs alone.

**`--help` is the authoritative reference for the edit sheet format.** It prints
the module docstring, which documents every row type. Read it before changing
the parser.

### Watching the result

```bash
ffplay -ss 300 -vf "ass=output/annotations.ass" output/master.mp4
```

VLC works too, but **press `v` to switch the subtitle track on** even though
it's flagged default. **Avoid IINA** — opening its chapter panel kills the
subtitle track, and you can't get back to 0:00 without restarting.

---

## Layout

Directories are named for the order the pipeline runs them.

| path | contents | in git? |
|---|---|---|
| `build.py` | the entire toolchain | ✅ |
| `normalize_and_join.sh` | raw → normalized → master | ✅ |
| `restore_raw_clips.sh` | fetch and verify footage | ✅ |
| `check_environment.sh` | machine readiness check | ✅ |
| `check_sheet.py` | validate the edit sheet without building | ✅ |
| `make_document.py` | build the written rubric — md, HTML, PDF, Word | ✅ |
| `make_manifest.sh` | regenerate `raw_clips.tsv` | ✅ |
| `annotations/` | the edit sheet — `01_intro`, `02_clips`, `03_appendices` | ✅ |
| `raw_clips.tsv` | manifest: sizes and SHA-256 | ✅ |
| `CLAUDE.md` | project state and working notes | ✅ |
| `raw/` | 37 source clips · 6.8 GB | ❌ release |
| `normalized/` | per-clip normalized video · 7.3 GB | ❌ rebuildable |
| `output/` | master, MKV, subtitles, chapters · ~14 GB | ❌ rebuildable |
| `junk/` | parked files, deliberately not deleted | ❌ |

Nothing tracked by git lives in a subdirectory, so ffmpeg can write whatever it
likes without `git status` noticing.

---

## Editing the video

All timings in the edit sheet are written against the **original, untouched
clip**. The script maps them through cuts, speed-ups, and inserted cards, so
adding a card or resizing an edit never requires re-timing anything by hand. See
`CLAUDE.md` §5 and `python3 build.py --help`.

---

## Republishing the footage

Only needed if the source clips ever change.

```bash
./make_manifest.sh                       # regenerate raw_clips.tsv from raw/
git commit -am "Update raw clip manifest"

# replace one clip in the existing release
gh release upload raw-footage-v1 "raw/NN - name.mp4" --clobber
```

GitHub replaces spaces with dots in release asset names;
`restore_raw_clips.sh` accounts for this when mapping assets back to filenames.
