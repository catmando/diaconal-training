# Hierarchical Divine Liturgy — Deacon Training Video

Claude Code reads this file automatically at the start of every session.

Last updated: 15 September 2026. Encode complete and in git, raw footage
archived off-machine, the edit sheet a YAML directory. The rubric is
published and **out for review**, so annotation edits now arrive in a
trickle — `check_links.py` (§14) is what keeps that from moving links people
already hold. The printed document carries **QR codes** that point at our own
page rather than at YouTube (§14). Service-book insert pages live in
`booklet/` (§16), and that toolchain has been extracted to a reusable
template repo.

---

## 1. The project

One training video for **deacons**, built from 37 short clips filmed at a
hierarchical Divine Liturgy, **20 June 2026**, OCA, Diocese of New York and
New Jersey (Archbishop MICHAEL; Metropolitan TIKHON). Each clip covers one
step of the service.

The video needs **explanatory text overlaid throughout** and **chapter
markers**. Annotations are rubric-level and choreographic: where to stand,
what to hold, which hand, what to say, and what cues trigger movement.

---

## 2. Where things stand

| | |
|---|---|
| Version control | **DONE.** github.com/catmando/diaconal-training (public) |
| Raw footage backup | **DONE.** 37 clips on the `raw-footage-v1` release; restore verified (§12) |
| Directory layout | **DONE.** `raw/` → `normalized/` → `output/` (§12) |
| Normalize encode | **DONE.** 37 clips → `normalized/001.mp4`…`037.mp4` |
| `master.mp4` | built, 1:03:23, now at `output/master.mp4` |
| Annotation timings | **FIRST DRAFT COMPLETE, all 37 clips, 24 Aug 2026** |
| Roles vocabulary | evolving by design (§6) |
| Roles chart | **ARRIVED 26 Aug 2026** (§6) |
| Chapter titles in MKV | **VERIFIED WORKING** on real footage (§8) |
| Edit sheet format | **DONE.** `annotations/`, split into three files 26 Aug 2026; CSV removed entirely (§4) |
| Rubric, published | **OUT FOR REVIEW** since 14 Sep 2026 (§14) |
| Printed QR codes | **DONE and LIVE**, 15 Sep 2026 — 34 section codes + masthead (§14) |
| Service-book inserts | pages 56, 64–65, 136–137 built and in appendix E (§16) |

---

## 3. One script does everything

`build.py`. It replaced the earlier `rebuild.sh`, `make_card.sh`,
`card_from_image.sh`, and `make_subs.py` — all obsolete, do not reintroduce.

```bash
python3 build.py                 # full build
python3 build.py --help          # flags AND the full sheet-format reference
python3 build.py --clip 3        # preview one clip (also 3-5 or 3,7,19)
python3 build.py --clip 3 --cards none   # preview times = the clip's own times
python3 build.py --clip 3 --draft        # ~4x faster re-encode, blocky
python3 build.py --clip 3 --play         # open in VLC if the build succeeds
python3 build.py --clip 3 --timecode     # burn ORIGINAL clip time on screen
python3 build.py --fade 1.5              # audio fade at each clip end (default 3, 0 = off)
python3 build.py --cut-fade 0            # audio fade into each cut (default 1.5, 0 = off)
python3 build.py --subs-only     # regenerate annotations only, fast
python3 build.py --sheet other.yaml
python3 build.py --speed 6       # default rate for spans saying speed: true
python3 build.py --no-mkv
python3 build.py --youtube       # burn subs into youtube.mp4, slow
```

**Outputs, all into `output/`:** `master.mp4`, `liturgy_training.mkv`
(chapters + annotations embedded, subtitle track flagged default),
`annotations.ass`, `chapters.txt`, `youtube_chapters.txt`, `boundaries.tsv`,
`thumbnails.tsv`.
Preview mode writes `output/preview.*` instead and leaves the real outputs
alone.

**A preview plays EDITED time; the sheet wants ORIGINAL time.** Once a clip
carries a cut, scrubbing the preview and reading the player's clock gives a
number that is wrong by however much the edits removed — and the user lost
work to exactly this on clip 4. `--timecode` burns the original clip time into
the corner of the preview, so the number on screen is the number to type.
Reach for it whenever a clip has cuts or speed spans.

**How the user works.** One clip at a time with `--cards none`, getting the
timing right before moving on; then every three or four clips together, with
cards, to check flow and adjust titles. So single-clip previews are the hot
path and must stay fast — a preview only edits the clips it will actually
show, and previews carry no media title, because VLC paints that tag over the
picture on every seek and it lands on top of the annotations.

**The sheet is validated before every build**, and errors stop it before
ffmpeg runs; `--no-check` overrides. `--cards none|leading|all` controls which
cards a `--clip` preview includes — `none` makes preview times equal the
clip's own times, which is what you want while timing text; `all` matches the
finished video.

Five supporting scripts, none of which touch the video: `check_sheet.py`
(the same validation, standalone — syntax, unknown keys, annotations past the
end of their clip, overlaps), `check_links.py` (prove a sheet edit did not
move a published link — §14), `check_environment.sh` (verify a machine can build —
run it before committing hours to a normalize pass), `restore_raw_clips.sh`
(fetch and SHA-256 verify the footage), `make_manifest.sh` (regenerate
`raw_clips.tsv`).

`normalize_and_join.sh` already ran. Do not run it again unless the source
clips change.

**`--help` is authoritative for the sheet format** — it prints the module
docstring, which documents every key. Read it before changing the parser.

---

## 4. The edit sheet — `annotations/`

**`python3 build.py --help` is authoritative** — it prints the module
docstring, which documents every key. Read it before changing the parser.
`python3 check_sheet.py` validates a sheet without building anything.

### Three files, read in name order

The sheet outgrew one file on 26 Aug 2026 and is now a directory:

```
annotations/01_intro.yaml         front matter, and the format reference
annotations/02_clips.yaml         the clips
annotations/03_appendices.yaml    the appendices
```

Every .yaml in the directory is read, **sorted by name** — which is what the
number prefixes are for. Splitting the clips further needs no code change:
add `02b_clips_20-37.yaml` and it falls into place. A file of nothing but
comments is skipped, so a header file is fine.

`build.py` holds the one loader, `load_sheet()`; `check_sheet.py` and
`make_document.py` import it rather than each opening YAML their own way.
A single file still works — `--sheet old.yaml` — and `default_sheet()` picks
the directory when it is there, so nothing had to change on the command line.

Errors name the file and the block: *"04_bad.yaml block 2: no heading"*.
That is the real gain of splitting, and it works across files — a duplicate
appendix id reports which other file already used it.

The original single file is parked at `junk/annotations.yaml.pre-split`.
The split was textual, not a YAML round trip, so every comment and every line
of prose survived unchanged: the generated rubric differed only by the build
stamp and the content deliberately added.

A list of clip blocks, in order. The clip number **is** the block, so it
cannot go missing.

The sheet may open with an **`intro:` block** — front matter for the written
rubric, which never reaches the video. It carries `title`, `subtitle`, and any
number of `sections:` of `heading` and `text`. Put introductory prose there
rather than in `make_document.py`: words meant to be revised belong with the
content they describe.

```yaml
- intro:
    title: Rubrics for Serving at a Hierarchical Liturgy
    subtitle: For deacons, subdeacons and altar servers
    sections:
      - heading: How to use this
        text: |
          …
```

**Appendices** are prose that belongs with the rubric but sits at no moment
in the video. **One block each**, and the value after `appendix:` is the label
the contents shows — `A`, `1`, `IV`, whatever suits:

```yaml
- appendix: A
  heading: Glossary
  text: |
    …
  image: art/roles_chart.png      # optional
```

They are chapters in their own right — listed in the contents and linkable —
but carry that id rather than a clip number, and no timecode. They appear in
file order; the id is a **label, not a position**, so reordering blocks does
not renumber them. Anchors are `#appendix-a`, from the id.

An earlier form nested them under `appendix: / sections:`. That is gone, and
`check_sheet.py` says so by name if it meets one.

```yaml
- appendix:
    sections:
      - heading: Glossary
        text: |
          …
```

An appendix section may also carry an **`image:`**, embedded the way the plan
diagrams are, and its `text:` supports **`[links](https://…)`** as well as the
usual emphasis. Links are set aside before the emphasis passes run, so an
underscore inside a URL is not mistaken for an underline.

### The roles card — `make_roles_card.sh`

Turns `Roles for Concelebrating Deacons.pdf` — itself an export of
`rubrics-for-2-8-deacons.numbers`, see §6 — into `art/roles_card.pdf`: the
chart on a Letter sheet inside a dashed 3⅜ × 5¼ in rectangle, to print at
**100%** and cut out to fit a service book. It also writes
`art/roles_chart.png` for the page and the printed document.
`make_document.py` copies the card into `docs/` so the site can serve it.

Three things that cost time and would cost it again:

- **The source page paints an opaque white rectangle over the whole sheet**
  before drawing anything (`0 0 612 792 re W n … 1 1 1 sc … f`). Anything drawn
  *under* the page content is therefore invisible.
- **Ghostscript's `/Install` procedure silently discards painting operators**
  with `pdfwrite`, while they still count towards the file's bounding box — so
  `gs -sDEVICE=bbox` reports marks that render nowhere. `/BeginPage` and
  `/EndPage` both paint properly. The cut marks go in `/EndPage`, which runs
  after the page content and so cannot be painted over.
- **`/Install` sets the device's DEFAULT matrix**, so an `initgraphics` inside
  `/EndPage` returns to it and marks inherit the content's scale. The content
  transform therefore goes in `/BeginPage`, leaving `/EndPage` in true page
  points.

The chart's own page number sits alone near the foot of the sheet. Including
it in the fit forced the table down to 53%; excluding it puts the table at
70%, a third larger. The script drops it by shrinking the media box to the
table alone in a first pass.

Both prose blocks are skipped by `build.py`, which is a thing to be careful
about: a block with no `clip:` used to be fatal, and that is exactly how the
`intro:` block broke the build (§8b). `build.py` now keeps the list in
`MATTER_KEYS`, and `check_sheet.py` imports it, so adding another prose block
type means changing one tuple. A block with neither `clip:` nor one of those
keys is still an error, so a misspelled `appendex:` is caught rather than
silently dropped.

```yaml
- clip: 1
  chapter: Greeting of the Hierarch at the Doors
  cards:        # played BEFORE this clip; `after: true` puts one after
  annotations:  # on-screen text and speed/cut spans, in time order
  notes:        # published — for the written document
  todos:        # the user's own; never on screen, never printed
  skip: true    # leave this clip out
  join: true    # continue the previous clip: no chapter, no fade between
  thumbnail:    # the moment to use as this section's poster on the web page
```

**`frame:`** on an annotation. The printed PDF shows the video frame beside
each cue, taken at the moment the annotation appears. `frame: no` leaves it
out — several cues in a row often share one unmoving camera, and a picture
that repeats the one above it costs a lot of page and says nothing. The Word
file and the web page carry no frames: the page has the video itself.

`build.py` writes `output/annotation_times.tsv`, keyed by clip and **position
in the sheet** — not by the text, which changes often, and not by position in
the time-sorted list, which agrees with sheet order only while the sheet is in
time order. A mismatch there puts the wrong frame beside the right words and
says nothing about it.

**`thumbnail:`** picks the still shown for this section on the written-rubric
page — one bare time, in **original clip time** like everything else, so
`--timecode` shows you exactly what to type. Leave it out and a frame is
chosen automatically: the longest run of footage in the section, a little way
in. The automatic choice deliberately steps over title cards, because a card
makes a useless thumbnail and every card looks like every other one.

`build.py` maps the time through the clip's cuts and speed spans and writes
`output/thumbnails.tsv`; `make_document.py` reads that and grabs the frame out
of `master.mp4`. Pointing a `thumbnail:` inside a cut is an **error**, not a
warning — that frame is not in the finished video at all.

Singular and plural are synonyms throughout: `annotation`/`annotations`,
`card`/`cards`, `cut`/`cuts`, `note`/`notes`, `todo`/`todos`. `thumb` is a
synonym for `thumbnail`.

**Timing.** Write times bare — `1:27`, `1:03:23`, `0:04`, `87`, `4.5`. On an
annotation `at:` (or `from:`) is the start and may be **left out**, in which
case it picks up 0.2s after the previous annotation ends, or at 0 if it is
the first in the clip. `for:` is a duration — leave it out and the annotation holds until the next
one starts, falling back to 4s when there is no next or its start is itself
relative. `to:` is an absolute
end, and **`to: end` runs to the end of the clip** — on spans too, so a cut
`from: 60, to: end` trims the tail. `at: next+1.5` waits longer. Resolves in
sheet order.

**Fades are deliberately asymmetric.** `--cut-fade` eases the sound down
*into* a cut but there is no fade in on the way out, because the user picks
cut end points at moments of silence — solving it in the edit rather than in
the encoder. Do not add a fade in unasked.

**Spans.** `speed:` and `cut: true` entries sit inline in the annotations
list so a clip reads in time order. Both ends must be given, and a span never
advances where the next annotation picks up. `speed: 4x` sets a rate;
`speed: true` defers to `--speed`. `audio:` is `mute` (default), `fast`
(time-stretched to fit, pitch intact but hurried) or `normal` (natural speed;
the opening of the span plays untouched for as long as the sped video lasts —
right for background singing — it holds full volume for `hold:` seconds,
default 4, then fades to silence rather than stopping dead). `mute:
true/false` is the older spelling of `mute`/`fast`.

**Cards** belong to the clip they are written under and play before it;
`after: true` puts one after. A skipped clip takes only its own cards with it.

**Chapters.** `chapter:` always means "a chapter starts here, titled this".
On a card it makes the card its own chapter, with a title that need not match
the words on screen; a card without `chapter:` folds into the chapter that
follows.

**Text.** Put prose under `text: >` or `text: |` — no quoting or escaping
ever. Blank lines are kept and render as a gap. `**bold**`, `*italic*` and
`_underline_` work anywhere; `#`, `##`, `###` set heading sizes on cards.
Cards render through libass, not drawtext, which is what makes more than one
size per card possible. Chapter names strip the markers. **Never put prose inside `{ }`**: a comma there ends the value and
silently swallows the rest of the sentence.

**A key cannot repeat in one block.** Writing `annotations:` twice parses
without error and discards the first list.
## 5. Everything is written against the ORIGINAL clip

Annotation times, cut times and speed times are all measured on the untouched
footage. The script maps them through the edits. So in a 3:00 clip:

```yaml
- clip: 7
  annotations:
    - from: 1:00
      to: 2:00
      cut: true
    - at: 2:30
      for: 4
      role: D1
      text: …
    - from: 2:45
      to: 2:55
      cut: true
```

the annotation lands at 1:30 and the second cut at 1:45. **Nothing is ever
re-timed by hand.** Adding cards, changing card durations, skipping clips, or
resizing an edit shifts nothing in the sheet.

The one exception: **trimming the head of a clip** shifts that clip's own
offsets. Tail trims are harmless. Nothing outside the clip is affected.

> A user asked why an annotation typed as `46` appeared at `0:54` — because an
> 8-second title card sits ahead of clip 1. Correct behaviour, not a bug.
> **Do not "fix" this.**

---

## 6. Deacon roles

Two deacons, treated as the normal case.

> **D1 (protodeacon) takes everything touching the hierarch directly** — the
> dialogues, censing of the bishop, the Gospel, the great commemoration, the
> diskos. **Litanies alternate beginning with D2.**

Clip 24 confirms D2 is last in the shoulder-kissing. (An earlier
`hierarchical_liturgy_cue_sheet.md` held a fuller table, but it was written
before the 37 clips were in hand and the user has confirmed it is no longer
needed — the footage supersedes it. Do not go looking for it.)

**The vocabulary is deliberately unsettled** — the user is working out which
roles are worth highlighting. Seen so far: `D1`, `D2`, `AS1+2`, `AS3+4`,
`DEACONS`, `PRIEST`, `CHOIR`. Any code gets a colour automatically.
**Do not push to freeze this.** Two open questions, not resolved: whether
`DEACONS` should be `D1+D2` for consistency, and whether long codes should
render smaller, since the role is a bold prefix that eats width.

**✅ The diocesan roles chart arrived 26 Aug 2026.** It covers **two through
eight** deacons (not one through four as expected), which means it answers
"more than two" thoroughly and says nothing about serving with one. Source
line on the original: Pdn. K. Sokolov, revised 1 June 2008.

**What is in the repo is not that original.** The user retyped and extended it
in Apple Numbers, and everything downstream is built from that:

    rubrics-for-2-8-deacons.numbers        the source — the only editable copy
      → Roles for Concelebrating Deacons.pdf   an export (= "… v3")
        → make_roles_card.sh
          → art/roles_card.pdf, art/roles_chart.png
            → appendix E, the printed cut-out card, the web page

Its own byline says so: *"Modified from original by Pdn. K. Sokolov 2008 by
Dn. M. VanDuyn 2026."* Every version of the PDF ever committed — back to the
first, 26 Aug — reports `Creator: Numbers`, so **the Sokolov original has
never been in the repo** and this file is the furthest back it goes. It went
in on 14 Sep 2026; until then the chart could not be regenerated from a fresh
clone at all. **To change the chart, edit the Numbers file and re-export** —
editing the PDF strands the source.

`Concelebration of Deacons v3.pdf` is byte-identical to the export and is a
second tracked copy of it, not a different document.

**It still has to be read against the annotations**: it is the thing that
could change annotation *text* rather than timings, and that pass has not been
done. Note for that pass: the chart assigns the trikirion and dikirion **by
deacon number, not by side**, so it says who carries them and nothing about
north/south or the crossing of §10.

---

## 7. Environment and traps

- macOS, zsh, Apple Silicon. ffmpeg 9.0.1 from the **`homebrew-ffmpeg/ffmpeg`
  tap** — the default brew formula lacked `drawtext` and `libass`.
- **The sheet is edited in VS Code, not a spreadsheet.** The CSV era ended
  because Numbers blanked the `clip` column on export — twice — silently
  dropping most annotations and then most chapter rows. In YAML the clip
  number is the block, so that class of failure is gone. Do not reintroduce
  a spreadsheet.
- **IINA bug:** opening the playlist/chapter panel and jumping chapters kills
  the subtitle track, and you cannot return to 0:00 without restarting. Use
  VLC, or `ffplay -ss N -vf "ass=annotations.ass" master.mp4`.
- **VLC needs the subtitle track switched on** (press `v`), even when flagged
  default.
- **YouTube silently drops ALL chapters** if any is under 10s, if the first is
  not 00:00, or if there are fewer than three. `build.py` warns.
- **Sparse annotations look like a bug.** Three times the user thought
  generation had failed when the cause was a long gap between timed
  annotations, or a preview containing only one chapter. **Check the actual
  event times before debugging anything.**

---

## 8. ✅ Resolved: chapter titles

Symptom: `liturgy_training.mkv` had 38 chapters with correct start times and
**no titles at all**.

Cause: `-map_metadata` copies *global* metadata; chapter titles are
per-chapter and need **`-map_chapters`**. The mux was missing it.

Fix applied to `build.py` and **now confirmed on the real footage** — a
`build.py --clip 3` preview mux produced `TAG:title=Entrance Prayers`, with
the subtitle track present and flagged default. Nothing further to do.

To re-check after any change to the mux:

```bash
python3 build.py --clip 3
ffprobe -v error -show_chapters output/preview.mkv | grep -i title
```

---

## 8b. ✅ Resolved: two bugs found 25 Aug 2026

Both were latent in the committed code and neither announced itself. Found
while wiring up poster frames, fixed and verified the same night.

**`build.py` could not read its own sheet.** The `intro:` block added for the
rubric has no `clip:`, and `read_sheet()` died on it — *"block 1 has no
whole-number clip"*. `check_sheet.py` and `make_document.py` both skipped
front matter; the build did not. So from the moment the intro was written,
**the video could not be rebuilt at all**, and nothing revealed it because
only `make_document.py` had been run since. `read_sheet()` now steps over it
like the other two.

**`--subs-only` dropped every card, and so mistimed everything.**
`add_cards()` returned early under `--subs-only` to avoid re-encoding cards,
but it returned *before* adding them to the sequence. Cards occupy real time
in the finished video, so every annotation, chapter mark and boundary came
out early by the total card length ahead of it — 22s by chapter 2, growing to
**5:25** by the end. It fails silently: the run looks normal and prints a
plausible total.

> Caught by comparing the reported total against the published video:
> **54:09 against 59:34**, a gap of 5:25 across 34 cards ≈ 9.5s each. After
> the fix the build reports **59:34.33**, and all 34 chapter times match the
> live page again. `make_card()` already skips an unchanged card, so the
> early return bought nothing.

The lesson worth keeping: `--subs-only` writes `chapters.txt`, and
`make_document.py` builds every video link from `chapters.txt`. A quiet error
there reaches the published page. **After any `--subs-only`, check the
reported total length against the video before regenerating the document.**

---

## 9. Coverage gaps

- **~18m after clip 20** — the homily. Deliberate. Card planned.
- **~27m after clip 33** — Lord's Prayer, elevation, fraction, communion of
  clergy and faithful. Neither notes nor footage cover it.

**The user has watched all the footage and asked not to keep raising these.
Respect that.**

---

## 10. Editorial cleanup, outstanding

**A full consistency pass is deferred until the first annotation draft is
finished** — the user's explicit instruction, so that wording is not polished
twice. This section is the running list; the user adds to it as things occur
to them. Do not start it early, and do not let it distract from the draft.

### Roles — get the vocabulary right first

The `role:` values are inconsistent already. Counted across the sheet on
24 Aug 2026:

    27  FIRST DEACON        6  ALTAR SERVERS       2  PRIEST
    26  SERVERS             5  SUBDEACONS          2  ALTAR SERVER
    18  SECOND DEACON       1  SUBDEACON           1  CHOIR
    13  DEACONS

Three spellings of the server role and two of subdeacon. Before normalising
the strings, settle the **substance**: is `SERVERS` the same office as
`ALTAR SERVERS`, and where does `SUBDEACONS` genuinely differ? A subdeacon is
tonsured and a server is not, and they do different things at a hierarchical
liturgy — so this is a question about accuracy, not tidiness, and the user's
priest and the footage decide it.

Only once that is settled: pick one spelling per office, singular or plural
consistently, and apply it everywhere.

### Content still to place

Things the user wants said somewhere, not yet written into the sheet.

- **When are the final bishop's prayers read?** The user does not know and
  intends to find out. Raised while looking at clip 3, where the first deacon
  *"reads the entrance prayers quietly, as normal, BUT stops before 'I will
  enter thy house'"* — so what happens to the remainder is an open thread.
  Clip 7 is titled *Final Prayers before the Liturgy*, which may or may not be
  the same moment; do not assume it is.

- **Deacons kiss the Holy Table before touching it.** Wanted in the
  introduction. Widely forgotten in parish practice, and a bishop will insist
  on it — which is the point worth making, and the reason it belongs early
  rather than buried at the moment it first applies.

### Left/right vs north/south — a real ambiguity, not just wording

Ten clips mention the dikiri and trikiri (6, 11, 12, 14, 15, 18, 20, 26, 27),
and they use **two different frames of reference**:

- clip 6: *"Dikiri on bishops **left** … trikiri on the **right**"* — the
  bishop's own body
- clip 15: *"Dikiri on the **right**, Trikiri on the **left**"* — the viewer's,
  as stated by the sentence that follows it

Both are correct, and both agree with the confirmed local practice. But read
one after the other they say the opposite, and the reader has to notice the
frame changed. **North and south are unambiguous whoever is facing where**,
which is why the diagram uses them. Prefer them in annotation text, or say
whose left is meant every single time.

### Then, wording

- Terms, case, spelling, grammar and punctuation across every annotation,
  card, chapter and note — one pass, at the end.
- Source notes skip section 11 and use 20 twice.
- Transliterations vary: *Ton Des Postin / Ton Despotin*; *Eis Polla Eti Thes
  Posta* (= *Eis polla eti, despota*); *Kolbuk / Klobuk*; *Matiya / Mantiya*;
  *Trikiri / Trikirion*. "**Jezel**" is Slavonic *zhezl*, the same staff called
  "Staff" elsewhere. Normalize; consider a glossary card.
- **Check the hierarchs' names** in the long commemoration before publishing.
- Clip 02 is titled "Bishop moves to the cathedra" but precedes the entrance
  prayers, while the notes put the cathedra after. Confirm against the footage.

### Dikirion and trikirion — which side, and the crossing

Researched 24 Aug 2026. The rule is sourced; the choreography is not.

**Sourced.** OrthodoxWiki: *"The trikirion is always on the bishop's right,
and the dikirion on his left"*, and they are kept *"respectively on the
northeast and southeast corners of the altar"* — dikirion northeast, trikirion
southeast. Those two agree, since a bishop at the Holy Table facing east has
his right hand to the south.

**Follows necessarily.** Facing **east**, trikirion is south and dikirion
north. Facing **west** toward the people, they reverse. So the bearers must
cross when he turns — the only way to keep the trikirion in his right hand
through a 180° turn. Not a local custom.

**Local practice, confirmed by the user:** at the Great Entrance the
**trikirion stands north and the dikirion south** — already set for the bishop
to bless the congregation, since facing west his right hand is to the north.
The Great Entrance diagram shows this arrangement, with the swap noted.

**Open, and not answerable from sources:** exactly *when* in the Great
Entrance they cross — before setting out, on the solea, or as he turns. The
user is confident the crossing always happens and cannot see it himself from
behind the Holy Table; he is asking **an experienced subdeacon in the
diocese**. (That person was the expected route to the roles chart of §6,
which has since arrived by another path.)

Worth showing in the Great Entrance diagram once confirmed, as arrows for Di
and Tr exchanging sides — it is precisely what the footage cannot show and
what the written sources are vaguest about.

---

## 11. Notes for whoever picks this up

- **Claude cannot watch video** — only metadata and extracted stills. Never ask
  for the clips.
- **Fix plain typos on sight, without asking.** The user's instruction,
  26 Aug 2026: a misspelling like *vidoe* or *simulatenously* is not a
  judgement call, so just correct it. This does **not** extend to wording,
  terminology or transliterations — those are the deferred consistency pass
  of §10, and *Trikiri* vs *Trikirion* is a decision, not a typo. When in
  doubt about whether something is a spelling or a choice, leave it and say
  so.
- **This is OCA / Russian recension.** Do not drift toward Greek or Antiochian
  usage.
- The user's priest and the footage are authoritative. Where this project
  infers, it says so. Keep that discipline.
- When something is broken, give commands **one at a time** and wait for
  output. Long multi-step blocks caused confusion more than once.
- Don't guess at causes. Twice tonight a confident diagnosis was wrong and the
  real cause only appeared after running the user's actual file. **Reproduce
  before explaining.**
- **State the plan before executing it.** The user asked for this explicitly.
  Say what you intend to do and wait for a go, especially for anything slow,
  outward-facing, or hard to undo. Read-only inspection to inform the plan is
  fine and expected.
- **Verify, don't assume.** Every claim in this file that says DONE was
  actually run. Follow that: prove the round trip, diff the output, check the
  real file.
- The user works on a **Mac laptop** (Apple Silicon, macOS). Cross-machine
  continuity means another Mac or a fresh clone after a disk failure — see §12.

---

## Files

| file | what |
|---|---|
| `build.py` | the entire toolchain |
| `annotations/` | the edit sheet, three files (§4) |
| `raw_clips.tsv` | manifest: size, SHA-256, duration, codec of all 37 clips |
| `normalize_and_join.sh` | raw → normalized → master; already run, don't re-run |
| `restore_raw_clips.sh` | download the footage from the release and verify it |
| `check_environment.sh` | verify a machine can build before committing hours |
| `check_sheet.py` | validate the edit sheet without building |
| `check_links.py` | prove a sheet edit did not move a published link (§14) |
| `published_links.tsv` | the blessed baseline `check_links.py` compares against |
| `make_document.py` | build the written rubric — markdown and HTML |
| `make_manifest.sh` | regenerate `raw_clips.tsv` |
| `make_roles_card.sh` | the roles chart → a card to print and cut out |
| `make_plate.sh` | a cut-out piece → a true-size PNG for the printed rubric (§16) |
| `booklet/` | service-book insert pages, set in the book's own type (§16) |
| `rubrics-for-2-8-deacons.numbers` | **the roles chart's source**; the PDF is an export of it (§6) |
| `README.md` | recovery runbook: bare Mac → finished video |
| `CLAUDE.md` | this file |

Three files this document used to list —
`hierarchical_liturgy_cue_sheet.md`, `clip_to_chapter_map.md`, and
`notes_for_hierarchical_divine_liturgy.pdf` — **no longer exist and are not
needed.** They were scaffolding from before the 37 clips were in hand. The
user has confirmed the footage supersedes them. Don't hunt for them, and
don't ask the user to re-supply them.

---

## 12. The repository and disaster recovery

**github.com/catmando/diaconal-training** — public, owned
by `catmando` (not the `catprintlabs` org, to keep it off company billing).

### ⚠ Renamed 15 Sep 2026, and the old name is a REDIRECT STUB

It was `hierarchical-liturgy-deacon-training`. Renamed to something short
enough to say aloud and type, **before** printed copies went out.

**GitHub Pages does NOT redirect a project site after a rename.** This was
verified, not assumed: seconds after the rename the old URL returned **404**
while the new one returned 200. Git remotes and `github.com` URLs do redirect;
the `github.io` site does not.

So **github.com/catmando/hierarchical-liturgy-deacon-training** now exists as
a tiny separate repo serving a redirect. `404.html` is the load-bearing half:
Pages serves it for any unknown path, so `/rubric.pdf` and `/#c26` are carried
across with path, query and fragment intact. It also **parks the old name**,
which a rename releases for anyone to claim. **Do not delete that repo.**

### A custom domain, later

Adding one does not invalidate printed QR codes: once a custom domain is set,
Pages redirects the `github.io` address to it, preserving the path. So paper
printed today survives it. Worth testing one code end to end before relying on
that at scale — and prefer a domain the user owns over a parish or diocesan
one, since the printed sheets outlive any arrangement over someone else's DNS.

### Layout

Directories are named for the order the pipeline runs them. Nothing tracked
by git lives in a subdirectory, so ffmpeg can write freely without ever
showing up in `git status`.

```
build.py, *.py, *.sh, raw_clips.tsv, README.md, CLAUDE.md
annotations/   the edit sheet: 01_intro, 02_clips, 03_appendices
raw/          37 source clips · 6.8 GB   — not in git; on the release
normalized/   build.py working files     — not in git; rebuildable
output/       master, mkv, subs, chapters — not in git; rebuildable
junk/         parked, deliberately not deleted
```

`junk/` exists because the user asked that nothing be deleted. Park things
there rather than removing them. It currently holds `test.mkv` and
`check.mkv`, 7.1 GB each.

### Why the footage isn't in git

6.8 GB, with 27 clips over GitHub's 100 MB per-file hard limit. Git LFS was
rejected deliberately: **LFS bandwidth is billed to the repo owner and
downloads by strangers count**, which on a public repo is an uncapped bill.
Release assets have no bandwidth metering and a 2 GB per-file ceiling, which
every clip clears comfortably.

### Recovery

Full runbook in `README.md`. The short version:

```bash
git clone https://github.com/catmando/diaconal-training.git
cd diaconal-training
./check_environment.sh          # tools, ffmpeg filters, font, disk, auth
./restore_raw_clips.sh          # 6.8 GB into raw/, SHA-256 verified
./normalize_and_join.sh         # hours; overnight; resumable
python3 build.py
```

**This path is tested, not theoretical.** Clip 01 was moved aside, recovered
from the release, and confirmed byte-identical; `make_manifest.sh` was
confirmed to reproduce the committed manifest exactly.

### Two traps worth knowing

- **GitHub rewrites release asset names**, turning spaces into dots:
  `01 - Greeting….mp4` is stored as `01.-.Greeting….mp4`.
  `restore_raw_clips.sh` maps them back via the manifest. Verified against
  the live API, not assumed.
- **ffmpeg must come from the `homebrew-ffmpeg/ffmpeg` tap.** The stock
  formula has shipped without `drawtext` and `libass`, which the title cards
  and the annotation overlay respectively depend on. `check_environment.sh`
  probes for exactly these.

### The source clips are not uniformly 30 fps

25 are 30 fps, six are 179/6 (≈29.83), five are 119/4 (≈29.75), and one is
120 fps. All 1920×1080 h264/aac, 63.4 minutes total. This is precisely why
`normalize_and_join.sh` exists — concatenating them raw produces broken
timing.

---

## 13. Plan diagrams — `art/`

Top-down plans of the church showing who stands where. They teach placement
better than the footage does, because a camera cannot show the whole floor at
once, and they carry no copyright encumbrance.

SVG is the source; the PNG the video uses is regenerated from it:

```bash
rsvg-convert -w 1920 -h 1080 art/great_entrance_plan.svg \
             -o art/great_entrance_plan.png
```

Used through an `image:` card, which is verified to work end to end:

```yaml
- clip: 26
  cards:
    - image: art/great_entrance_plan.png
      for: 10
      chapter: The Great Entrance — positions
```

Give a diagram ~10s, not the 6 a title card gets — it has to be studied.

| file | what |
|---|---|
| `church_plan.svg` | bare architecture, the starting point for new diagrams |
| `great_entrance_plan.svg` | the procession once outside the altar |

**The greeting plan was wrong until 28 Aug 2026** and is now corrected against
**experienced subdeacons of the diocese**, who is the authority for it:

- **D1 stands on the south line, D2 on the north** — they were the other way
  round.
- **Seniority runs toward the bishop, not toward the altar.** The senior
  priests stand nearest the doors, where the bishop is, and the junior toward
  the altar. The diagram had it reversed.

Neither is guessable from the footage, which is why it stood wrong for a
fortnight. The censing annotation's "from senior to junior, and south to
north" is a different moment on a different axis and does not conflict.

**The Great Entrance plan is confirmed correct by the user**, including the
inferred architecture. Convention: east at the top, so north is left and
south is right. Marker colours follow the on-screen role colours.

Worth drawing next, all reusing `church_plan.svg`: the vesting, the little
entrance, censing paths, and the order of shoulder-kissing.

### Wanted, once the first draft is done: diagrams beside the video

The user wants a diagram shown *alongside* the footage rather than as a card
that interrupts it — pictorial annotation. Deliberately deferred until the
annotation pass is finished; do not start it early.

The mechanism already exists in the codebase. `burn_timecode()` overlays a
drawtext per segment switched on with `enable='between(t,S,E)'`; a diagram is
the same shape with `overlay` instead, and the annotation timing model
supplies the spans for free. Sketch:

```yaml
    - at: 1:20
      for: 20
      image: art/great_entrance_plan.png    # beside the picture, not a card
      text: Positions once outside the altar
```

Two things to decide when it is built. Whether the video shrinks to make room
(a real layout change, and every annotation position would move) or the
diagram floats over a corner (cheap, but covers footage). And that it means
re-encoding, like `--timecode` — so it belongs in the burn step rather than
in `master.mp4`, or previews get slow again.

---

## 14. Published

**Video:** https://youtu.be/aRs9oqKMCd8 — unlisted, 59:34, 35 chapters,
annotations burned in. Built 25 August 2026 from `build.py --youtube`.
An earlier cut at `o8MRc9T90hY` is superseded: it lacks the greeting plan
card, so every chapter after the first sits 10s earlier.

**Written rubric, online:**
- https://catmando.github.io/diaconal-training/ — the
  styled version, served by GitHub Pages from `docs/index.html`
- https://github.com/catmando/diaconal-training/blob/main/RUBRIC.md
  — the same words, rendered by GitHub itself

Both are **public and indexable**, unlike the unlisted video. `RUBRIC.md`,
`docs/index.html`, `docs/posters/` and the two download files are the only
generated things that are committed; everything in `output/` stays ignored.

**Published 25 Aug 2026** with poster frames, the section reset control and
four appendices. All 34 chapters kept their id, title, timecode and player
span through that change, so links already sent out still land where they
did — worth re-checking the same way after any future regeneration, since
about five people were holding the link at the time.

### The published file names

`printed.pdf` and `printed.docx` — renamed from `rubric.*` on 15 Sep 2026,
with the repo, so an address can be said aloud. `index.html` stays as it is:
it is what makes the bare URL work, and the bare URL is the easiest thing of
all to type.

    catmando.github.io/diaconal-training/                the page
    catmando.github.io/diaconal-training/printed.pdf     the printed copy

The masthead carries that address **in words as well as in code** — a QR is
useless to anyone without a phone in their hand.

### `--draft` — the watermark

```bash
python3 make_document.py --draft --video https://youtu.be/aRs9oqKMCd8
```

A flag, deliberately, and not a default: neither a watermarked final nor an
unmarked draft can then happen by accident. `--draft "SOME TEXT"` for a
different word.

One `position:fixed` element does every page — WeasyPrint repeats a fixed box
on each one — and the same rule serves the web page, where it is
`pointer-events:none` so it cannot intercept a click.

**It is light for a reason that is not taste.** The QR codes carry no white
backdrop of their own; the page's white *is* their quiet zone, so ink laid
across them eats into it. At 7% black it binarises as white and every code
still reads — **verified by decoding all 35 with the watermark on.** If that
colour is ever darkened, decode them again before printing.

### ⚠ QR codes on the printed page — and why they point at US

Added 15 September 2026, live the same day. **34 section codes plus one on
the masthead.**

Before this, the printed document had **no working route to the video at
all**: `rubric_print.md` is built with links off, and the print stylesheet
hides the poster and player (`.player,.pctl{display:none}`). The 34 section
links existed only as dead text.

**The codes do NOT point at YouTube, and that is the entire point.**

> YouTube will not let a video's file be replaced. Any re-upload mints a new
> id — §14 records `o8MRc9T90hY` being superseded exactly that way — and a
> printed sheet cannot be recalled. A code pointing at a YouTube id is frozen
> the moment it is printed.

So each section's code is:

    https://catmando.github.io/diaconal-training/?play=c26#c26

Our own page. A re-upload, a decision to publish the 37 clips separately, or
leaving YouTube altogether is absorbed by **regenerating the page** — the
paper stays correct. The page is an indirection layer, and that is worth more
than the two extra QR modules it costs.

It also fixes what prompted the work: **a bare YouTube link only starts, it
never stops.** The section ran on into the next. There is no URL that bounds
it — the watch page has no end parameter, and the embed player's `end=` was
already tested here and rejected (see the END_GUARD comment: *"YouTube's own
`end` cannot be trusted"*).

### The `?play=cN` contract

`END_GUARD` in `make_document.py` reads `?play=` on arrival and:

1. scrolls to that section,
2. opens its player in a **full-screen overlay** — black, with a × button,
   Escape to close,
3. lets the existing guard stop it at the section boundary, then closes the
   overlay and leaves the reader on that section's **text**.

**Not the Fullscreen API.** It needs a user gesture; a scan is a navigation,
so `requestFullscreen()` is refused, and on iOS it does not apply to an
iframe at all. A fixed overlay needs no permission and behaves the same
everywhere. The reader can still reach true fullscreen from the player's own
button, because tapping that *is* a gesture.

**Autoplay is the browser's decision.** If a phone refuses, the player is
built and sitting at the right second and one tap runs it. That is not a bug;
do not "fix" it.

The code carries **both** `?play=c26` and `#c26`, so with no JavaScript the
reader still lands on the right section.

### Things that cost time here, and would again

- **The still and the QR must be the same height, and a QR image normally
  carries its quiet zone INSIDE the picture.** Both boxes were 0.9in with
  centres coinciding exactly, and the code still looked short beside the
  photo, because its ink was only 0.803in. Generated with `border=0` the
  image *is* the symbol, so a 0.9in box holds 0.9in of ink at any version.
  The page's own white supplies the quiet zone, and the stylesheet keeps four
  modules clear on every side. It also made the codes **more** robust — they
  decode down to 75 dpi where before they failed below 110.
- **A float narrows the LINES beside it, not the block box.** The first
  attempt ran the grey ON SCREEN card's background under the still and the
  caption under the first cue's text. `.chapter blockquote.card,.chapter
  ol.cues,.chapter figure{clear:right}` fixes it, and the card is emitted
  *before* the `<h2>` so the title flows alongside rather than below.
- **Do not size the overlay with `100vw`/`100dvh`.** With width and height
  both set it is over-constrained against `inset:0`. `inset:0` alone already
  means "the viewport" and tracks a phone's collapsing address bar.
- **A headless screenshot of this page comes out blank** even when the DOM
  and computed styles are correct. Do not debug the CSS from it — inject a
  diagnostic that reports `getBoundingClientRect()` and computed styles into
  the DOM, and read that back with `--dump-dom`. An hour went into a blank
  PNG that was a capture artifact.
- **chromedriver on this machine is version 150 against Chrome 154**, so
  WebDriver sessions will not start. `--headless=new --dump-dom` works.
- **Pages does not swap every file at once.** After the push the new
  `rubric.pdf` was live about a minute before the new `index.html`, so there
  is a brief window where a scanned code reaches the old page. It resolves
  itself; just do not panic-republish.

How to re-verify the whole chain after any change:

```bash
python3 make_document.py --video https://youtu.be/aRs9oqKMCd8
pdftoppm -png -r 300 docs/printed.pdf /tmp/p        # then zbarimg each page
python3 check_links.py --live
```

Every code must decode, and every `?play=cN` must name a section id that
exists in the live page.

### Checking that a link still lands — `check_links.py`

The rubric went out for review on 14 Sep 2026, so annotation edits now arrive
in a steady trickle and the number of people holding links only grows. This
script is what makes that safe. Written and verified 15 Sep 2026.

**Most edits are free.** Times are written against original clip time (§5), so
changing an annotation's `text:`, `role:` or `notes:` moves nothing at all.

**These are not.** Adding, removing or resizing a **card**; editing a **cut**
or **speed** span; `skip:` on a clip. Each shifts every chapter time after it.
In `git diff` of the sheet that looks exactly like a wording change, and §8b
is the reminder that the failure is silent — the build prints a plausible
total and the wrong times reach the page.

Three separately breakable addresses per section, which is why the check
exists at all:

| address | comes from | breaks when |
|---|---|---|
| `#c26` in the page | the **clip number** | the section stops existing |
| `#the-great-entrance` in `RUBRIC.md` | the **title**, slugged | the title is reworded |
| `data-start` / `data-end` | `chapters.txt` | anything ahead changes duration |

```bash
python3 check_links.py            # what moved since the last publish?
python3 check_links.py --live     # ...and is the baseline what is being served?
python3 check_links.py --bless    # record this state as published
```

Exit status is 1 when something moved, so it can gate a publish. The baseline
is `published_links.tsv`, **committed** so it travels with the repo.

**`--bless` is a deliberate act, done AFTER a successful publish**, never
before — blessing a broken state is the one way to defeat the whole thing.

Two things it catches that are easy to miss. **The page looks its times up by
title**, so two sections sharing a title silently both get the first one's —
warned about on every run. And **`--live` reads the site**, not HEAD, which is
§14's own rule about where the truth is.

Verified on the real thing when written: blessed from the local build, and
`--live` confirmed all 34 sections match what GitHub Pages is serving. Then
doctored baselines confirmed it actually fails — a reworded title, a start
moved 10s, a section removed, and a section that no longer exists each
reported, exit 1. A guard that has only ever said OK is not a proven guard.

`docs/staging/` is deliberately **untracked**. It cannot reach the site, and
that is what makes it safe: publishing is `git add` of explicit paths, never
`git add docs/`. It is left on disk rather than deleted, per the project's
no-deletion rule.

One wrinkle to expect: the build stamp on the page names the commit that was
checked out when the page was *generated*, which is the commit before the one
that publishes it. That is accurate rather than wrong, but it does mean the
stamp always trails the publishing commit by one.

**Written rubric:** `make_document.py` builds it from the same sheet, so it
cannot drift from the video. Regenerate whenever either changes:

```bash
python3 make_document.py --video https://youtu.be/aRs9oqKMCd8
```

It writes five files into `output/`: `rubric_online.md`, `rubric_print.md`,
`rubric.html`, and — when `weasyprint` and `pandoc` are installed —
`rubric.pdf` for printing and `rubric.docx` for Word. Both diagrams survive
into the PDF and the Word file.

```bash
brew install weasyprint pandoc     # once, if the last two are wanted
```

Chapter headings then link into the video at the right second. Always
regenerate *after* a rebuild — the timings come from `output/chapters.txt`,
so a stale document sends readers to the wrong moment.

---

### Poster frames on the rubric page

Every section on the page shows a **still from that section** with a play
button, not a YouTube embed. Clicking one builds the real player; at the
section end the player is **destroyed and the still put back**.

That teardown is not cosmetic. A player left paused on its last frame resumes
from where it stopped, so a second click would run on into the next section.
Rebuilding from the poster re-applies `start` every time, which is the only
way a bounded section replays correctly.

A **"Back to the start"** button appears under the section that is playing,
and only that one, doing the same teardown on demand — without it the only
way back to the still was to let the section run out. Its row keeps its
height whether the button shows or not, so starting a section does not shove
the rest of the page down.

Two things follow, and both are the point:

- **Each section looks like itself.** YouTube cannot do this — the poster is
  a property of the video, not the embed, so all 34 sections would otherwise
  show the one thumbnail. The stills come out of `master.mp4`.
- **The page contacts YouTube only on a click.** Not even the IFrame API is
  fetched before that. Verified in headless Chrome: 34 posters and **zero**
  iframes at load; one click yields exactly one iframe with
  `start`/`end`/`autoplay` set, and the other 33 posters untouched.

Posters are **files** in `posters/` beside the page, not data URIs, so
changing one `thumbnail:` rewrites one small JPEG instead of the whole
page — which is what keeps the git history of a 34-poster page sane. They are
grabbed only when the moment changes, tracked in `posters/index.tsv`. 34
posters cost about 850 KB.

Autoplay after the click is the browser's decision. It works in Chrome and
usually in Safari; if a browser refuses, the reader sees a loaded, paused
player and clicks once more. Nothing breaks.

### Prose, and the two versions of it

Text in `intro:` and `appendix:` blocks is **prose**, and differs from a card
or an annotation in three ways that all cost time to discover:

- **Line breaks reflow.** A newline in prose is only where the line was
  wrapped in the editor, so the lines are joined and the paragraph flows to
  the reader's width. On a card or an annotation a newline is deliberate —
  the video shows it that way — so it stays a `<br>`. Getting this wrong
  reproduces the editor's wrapping on screen and strands the last word of a
  line by itself.
- **Emphasis may span lines**, because the lines are joined before the
  `*italic*` pass runs. It still may not on a card.
- **Images can sit inline**, written as ordinary markdown on a line of their
  own. `image:` on the block only ever hangs one off the end, which is no
  use when a sentence says "the following chart".

```yaml
![Roles for concelebrating deacons](art/roles_chart.png "card")
```

The `"card"` after the path means: on paper this is a thing to cut out. See
below. Paths are rewritten per output — `art/…` in `RUBRIC.md`, `../art/…`
in the `output/` copies, a data URI in the web page.

**A paragraph may open with `@screen` or `@print`** and is kept only for that
one; unmarked paragraphs, nearly all of them, appear in both.

**Since 15 Sep 2026 the same markers work on a ONE-LINE field** — a heading,
or the colophon. The versions are written one per line and the matching one
is taken; an unmarked line is used for both, so nothing in the sheet had to
change when this was added:

```yaml
- heading: |
    @screen How to use this webpage
    @print  How to use this document
```

This exists because the front matter genuinely says different things now: on
screen the reader presses play, on paper they scan a code. `line_for_medium()`
does it, beside `for_medium()`, and `check_sheet.py` validates headings the
same way it validates paragraphs — a mistyped `@sceen` in a heading is
rejected by name.

**The colophon lives in the sheet, not in the code.** It used to be a
hardcoded string in `make_document.py`, which broke this project's own rule
that words meant to be revised belong with the content. It is now
`colophon:` in the `intro:` block and takes the markers like any prose. This exists
because a download link is useful on screen and pointless on paper, where the
same thing is a page you can already cut out:

```yaml
@screen A printable version is available: [download the card](…).

@print The chart is repeated overleaf at the size it should be cut to.
```

The alternative — code that knows which sentence to drop — breaks silently
the first time the sentence is reworded. `check_sheet.py` rejects a mistyped
marker, so `@sceen` is an error rather than a paragraph that quietly appears
in both.

Which copy is which medium: `docs/index.html` and staging are **screen**;
`output/rubric.html` is **print**, because weasyprint turns it into the PDF;
`rubric_online.md` and `RUBRIC.md` are screen, `rubric_print.md` and so the
Word file are print.

### ⚠ The printed PDF is US Letter, and was A4 for months

`@page{ size:letter }` is load-bearing. **WeasyPrint defaults to A4**, and the
stylesheet never said otherwise, so every PDF built before 26 Aug 2026 was
A4. A US printer asked to fit A4 onto Letter scales it by about 94% — which
would have made the cut-out card the wrong size with nothing to indicate why.
This is a US parish; the document is Letter.

The page also declares **`<meta charset="utf-8">`**. Without it the page
depends on the server sending a charset: GitHub Pages does, but
`python -m http.server` sends a bare `text/html`, so a locally-served page
falls back to Windows-1252 and every em dash renders as `â€"` — a fault that
appears only when reviewing locally and vanishes on publishing, which is the
worst way round. Same family as the weasyprint mojibake that needs
`--encoding utf-8` spelled out: **UTF-8 in the file is not enough, every
consumer has to be told.**

### A card to cut out of the printed document

An inline image marked `"card"` gets a sheet to itself when printed: the
image at its true size inside a dashed cut line, caption below it and outside
the line so it goes with the offcut, and **the back of that sheet blank** —
"This page is intentionally blank, so the chart overleaf can be cut out."
Printed duplex, that sheet can be pulled and cut without losing anything.

It works by `break-before:right` on the figure, which starts it on a front
(odd) page; the blank page then falls on the back of that same sheet.
Verified at 600 dpi: the cut rectangle measures 243.00 × 377.88 pt — 3⅜ × 5¼
inches, the 0.12 being one pixel.

### Previewing before publishing — use localhost

There is no staging mode. `make_document.py` writes `docs/`, a local server
points at `docs/`, and **nothing is public until it is pushed**:

```bash
python3 make_document.py --video https://youtu.be/aRs9oqKMCd8
cd docs && python3 -m http.server 8000        # then open localhost:8000
```

Publishing is `git add` of the generated files, commit, push. Throwing a
preview away is `git checkout -- RUBRIC.md docs/`.

A `--staging` mode existed for a day, writing a parallel copy under
`docs/staging/`, and was removed on 26 Aug 2026: once the local server was
the review path, two URLs differing only by a `/staging/` suffix cost more
than they protected — the wrong one was opened twice. The old copy is parked
in `junk/`.

**Check the printed PDF too, not only the page.** They deliberately say
different things now (§ *Prose, and the two versions of it*), so looking at
one is not looking at the other.

Two things to be careful of, both learned the hard way:

- Generating writes the **published files**. That is fine — they only reach
  the site on a push — but if a run is interrupted part way, some are
  rewritten and others are not. `for_github()` writes `RUBRIC.md` and
  `docs/index.html` before the PDF is built, so an interrupt between them
  leaves a mismatched pair. `git status` shows it; `git checkout` fixes it.
- **Verify a restore against the live site, not against HEAD.** HEAD is only
  what was last committed, which is not necessarily what is being served.

  ```bash
  curl -s "https://catmando.github.io/diaconal-training/?cb=$(date +%s)" \
    | diff - docs/index.html && echo "identical to what is live"
  ```

- **Push the code with the output.** The publish of 26 Aug went out while
  `make_document.py` was still uncommitted, so for a few minutes the site
  carried a PDF the committed code could not reproduce. Commit the generator
  and the generated together.

---

## 15. Distribution — thought about, not decided

Raised 21 August 2026 while the user was at clip 9 of 37. Nothing is built;
this records the analysis so it does not have to be redone.

### Size

`master.mp4` is **6.5 GB at 15.3 Mbps** — archival, more than handing out
needs. Measured from a 30s sample scaled to the full 63 minutes:

| target | full video |
|---|---|
| current, CRF 18 | 6.5 GB |
| 1080p CRF 24 | 4.0 GB |
| **1080p CRF 26** | **3.0 GB** |
| 1080p CRF 28 | 2.2 GB |
| 720p CRF 23 | 2.2 GB |

**Stay at 1080p.** At equal file size, 720p makes the annotation text mushy —
text suffers from downscaling far more than the footage does.

### Three traps for a thumb drive

- **Format the drive exFAT, not FAT32.** FAT32 caps a single file at 4 GB, and
  a larger copy fails part way through, sometimes without a clear error. Most
  drives ship FAT32. This is the likeliest way a handout day goes wrong.
- **Do not hand out the MKV.** Its annotations are a subtitle *track*:
  QuickTime will not open MKV at all, Windows needs VLC, and VLC still needs
  `v`. Distribute mp4 with the text **burned in** — it plays everywhere and
  needs no instructions.
- **A burned-in mp4 has no chapter menu.** Put `chapters.txt` on the drive as
  a plain listing.

### Online

**YouTube unlisted** is stronger than a drive for most people: free, plays on
any phone or TV, nothing to lose, and chapters work — `youtube_chapters.txt`
is already generated. Unlisted is not searchable; only a link reaches it.
Caveat the user should weigh deliberately rather than inherit from the GitHub
decision: the footage shows identifiable clergy and parishioners, and YouTube
is a different reach from a public repo.

A GitHub release asset is the other free option, but assets cap at 2 GB per
file, which a 3 GB video clears only if the quality drops further.

### Still to build

- **`--distribute`**: burned-in text, 1080p CRF 26, `+faststart`, chapters
  beside it. `--youtube` exists but burns at CRF 18 / preset slow and would
  produce roughly 9 GB, which is wrong for this.
- **The written document.** `notes:` fields are collected for it and nothing
  generates one yet — the user chose "carry the field only" when the format
  was designed. It is what would make a thumb drive a package rather than a
  video file.

---

## 16. Service-book insert pages — `booklet/`

Pages set in the **parish liturgy book's own type**, printed and pasted into
the book where a hierarchical liturgy departs from the ordinary one. They
reach the reader as **appendix E, "Pages to Cut Out"** — a download link on
screen, a true-size plate on paper.

**This is ordinary parish practice.** Pasting corrections into a service book
is normally done by hand; this only makes a printed one. The fitting, the
paper and the glue are the user's own well-trodden ground — **do not offer
advice about them.** The job here is the typography and the words.

| page | what | size |
|---|---|---|
| 56 | completion of the vesting | single leaf, 3.625 × 5.875in |
| 64–65 | entrance prayers, with *Ton Despótēn* | spread, 7.25 × 5.875in |
| 136–137 | great commemoration through *Is Polla Eti Despota* | spread |

```bash
cd booklet && python3 make_insert.py 136     # pages/136.txt -> insert_136.pdf
./make_plate.sh booklet/insert_136.pdf art/insert_136_137.png 7.25 5.875
```

`booklet/SPEC.md` is authoritative for the measurements, and
`make_insert.py --help` for the markup. Content is one plain text file per
piece in `booklet/pages/`, using deliberately the same `**bold**`/`*italic*`
as the annotations sheet.

**The measurements were taken off a 450 ppi scan, not guessed**: page
3.625 × 5.875in, measure 203.5pt, body x-height 4.55pt, leading 14.2pt, red
`#d80c18`.

Three things that cost real time:

- **Match the x-height, never the nominal point size.** The book is
  Jenson/Centaur (probably Adobe Jenson); the build uses **Junicode** (OFL).
  Junicode's x-height runs small, so the body is **11.7pt**, giving 4.56pt
  against the measured 4.55.
- **At that size the regular cut sets ~11% wide**, so a page held fewer words
  than the book's. The condensed axis (`wdth 75`) restores it. The test is
  the opening paragraph setting in 6 lines, exactly as the book does.
- **Hyphenation needs `pyphen`** (`pip3 install --break-system-packages
  pyphen`). Without it WeasyPrint silently sets justified text with no
  hyphens and the word spacing falls apart — which looks like a font problem
  and is not.

**Text that does not fit is silently lost**, spilling into a column beyond
the sheet's trim. Every build reports the fit; believe it.

Still open, recorded in `SPEC.md`: **page 137 is invented placeholder text and
must be replaced**, and page 136 is transcribed from the scan and OCR-agreed
but wants a human proofread before anything is glued into a book.

### Extracted for reuse — `STOTS-typica-template`

15 Sep 2026: the toolchain was extracted to
**github.com/catmando/STOTS-typica-template**, a public GitHub *template*
repo (press "Use this template" to start a project). `page.css` is the layout
machinery and contains no measurement of any book; `book.toml` **is** the
book, and ships the STOTS measurements, so an insert into that book needs no
measuring at all.

Verified by rebuilding all three pages here through the extracted tool and
comparing with the PDFs already in use: **pixel-identical**. A fresh clone
reproduces them too. `head_top`/`rule_top` ship as 0.116/0.176 rather than the
measured 0.115/0.175 — a thousandth of an inch, and these are the numbers
that produced the pages already pasted into books.

`booklet/` here is **untouched** and still works standalone. Pointing it at
the template is a separate job, not yet done.
