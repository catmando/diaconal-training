#!/usr/bin/env python3
"""Build the written rubric from the edit sheet.

    python3 make_document.py
    python3 make_document.py --video https://youtu.be/XXXX
    python3 make_document.py --sheet other.yaml

Writes two files into output/:

    rubric_online.md   linked contents, timecodes hyperlinked to the video
    rubric_print.md    no links, page breaks between chapters
    rubric.html        the same, styled and self-contained
    rubric.pdf         for printing        (needs weasyprint)
    rubric.docx        for editing in Word (needs pandoc)

Two more are written outside output/, because they are meant to be committed
and read on GitHub:

    RUBRIC.md          rendered by GitHub in the repository itself
    docs/index.html    served by GitHub Pages, styled, diagrams and all

The last two are written only if those tools are installed:

    brew install weasyprint pandoc

Both carry the same words. The online one is for reading beside the video;
the printed one is for the ambo, the vestry, or a pocket.

What goes in, and what does not:

    chapter:      becomes the section heading
    cards:        the words on screen, shown as a quotation
    image:        diagrams are embedded
    annotations:  the timed directions, with role and timecode
    notes:        published prose, printed under the directions
    todos:        NEVER — those are the user's own

Timecodes are positions in the ORIGINAL clip, matching the sheet. Chapter
headings additionally carry their position in the finished video when
output/chapters.txt is present from a full build.
"""
import argparse, base64, datetime, html, io, mimetypes, os, re, shutil
import subprocess, sys

try:
    import yaml
except ModuleNotFoundError:
    sys.exit("ERROR: PyYAML missing — pip3 install --break-system-packages pyyaml")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_sheet import resolve, clip_durations, is_span, as_list, _first
from build import load_sheet, default_sheet

OUT = "output"

# Where the published page lives. The printed QR codes point HERE rather than
# at YouTube, which is the whole reason they keep working: see qr_uri().
SITE = "https://catmando.github.io/diaconal-training/"


def build_stamp():
    """When this was generated and from which commit, so it is obvious at
    a glance whether the page in front of you is the current one."""
    when = datetime.datetime.now().strftime("%d %b %Y, %H:%M")
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True).stdout.strip()
    except Exception:
        sha = ""
    return f"generated {when}" + (f" \u00b7 {sha}" if sha else "")


def mmss(t):
    t = max(float(t), 0)
    h, m, s = int(t // 3600), int((t % 3600) // 60), int(t % 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def md_escape(t):
    """The sheet's own emphasis is markdown already, so only table-breaking
    pipes need dealing with."""
    return str(t).replace("|", "\\|")


def video_chapters(path=os.path.join(OUT, "chapters.txt")):
    """[(title, start, end)] from a full build's FFMETADATA chapters.

    A chapter's own END runs past the next chapter's START, because a leading
    card pulls the next chapter backwards to cover it. So a chapter really
    ends where the next one begins; only the last keeps its own END.
    """
    rows, start, end = [], None, None
    if not os.path.exists(path):
        return rows
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line.startswith("START="):
            start = int(line[6:]) / 1000.0
        elif line.startswith("END="):
            end = int(line[4:]) / 1000.0
        elif line.startswith("title=") and start is not None:
            rows.append([line[6:], start, end])
            start = end = None
    for i in range(len(rows) - 1):
        rows[i][2] = rows[i + 1][1]
    return [tuple(r) for r in rows]


def video_chapter_starts(path=os.path.join(OUT, "chapters.txt")):
    """title -> seconds."""
    out = {}
    for t, st, _en in video_chapters(path):
        out.setdefault(t, st)
    return out


POSTER_W    = 560      # poster width in px; the column is ~700 at most
POSTER_Q    = 6        # ffmpeg -q:v, 2 best .. 31 worst
AUTO_LEAD   = 14.0     # seconds into a section for an automatic grab
AUTO_FRAC   = 0.35     # ...or this far through it, whichever is sooner
MIN_RUN     = 1.0      # a stretch of footage shorter than this is not worth
                       # grabbing from, and absorbs cross-file rounding
MASTER      = os.path.join(OUT, "master.mp4")


def declared_thumbnails(path=os.path.join(OUT, "thumbnails.tsv")):
    """clip -> seconds into master.mp4, from a `thumbnail:` in the sheet.

    build.py writes this, because only it knows how the cuts and speed spans
    move a time written against the original clip. Absent file means nobody
    has declared one yet, which is the normal state early on.
    """
    out = {}
    if not os.path.exists(path):
        return out
    for i, line in enumerate(open(path, encoding="utf-8")):
        if i == 0 or not line.strip():
            continue
        bits = line.rstrip("\n").split("\t")
        if len(bits) < 2:
            continue
        try:
            out[int(bits[1])] = float(bits[0])
        except ValueError:
            pass
    return out


def poster_frames(jobs, outdir):
    """Grab one still per section out of master.mp4.

    jobs is [(name, seconds)]; returns name -> filename relative to outdir.
    Files are kept rather than inlined, so a regeneration that changes one
    thumbnail rewrites one small JPEG instead of the whole page — which is
    what keeps the git history of a 34-poster page reasonable.
    """
    if not os.path.exists(MASTER):
        print(f"  posters skipped — {MASTER} not found (run build.py)")
        return {}
    d = os.path.join(outdir, "posters")
    os.makedirs(d, exist_ok=True)

    idx_path = os.path.join(d, "index.tsv")
    have = {}
    if os.path.exists(idx_path):
        for line in open(idx_path, encoding="utf-8"):
            bits = line.rstrip("\n").split("\t")
            if len(bits) == 2:
                have[bits[0]] = bits[1]

    made, grabbed = {}, 0
    for name, secs in jobs:
        fn = f"{name}.jpg"
        made[name] = f"posters/{fn}"
        stamp = f"{secs:.3f}"
        full = os.path.join(d, fn)
        if have.get(name) == stamp and os.path.exists(full):
            continue          # same moment, already grabbed
        r = subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-ss", stamp, "-i", MASTER,
             "-frames:v", "1", "-vf", f"scale={POSTER_W}:-2",
             "-q:v", str(POSTER_Q), full],
            capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(full):
            print(f"  poster {name} failed:", (r.stderr or "").strip()[:100])
            made.pop(name, None)
            continue
        have[name] = stamp
        grabbed += 1

    with open(idx_path, "w", encoding="utf-8") as f:
        for name in sorted(have):
            if name in made:
                f.write(f"{name}\t{have[name]}\n")

    kb = sum(os.path.getsize(os.path.join(d, f"{n}.jpg"))
             for n in made) / 1024
    print(f"  {d}/   {len(made)} posters, {kb:.0f} KB "
          f"({grabbed} freshly grabbed)")
    return made


FRAME_W = 360          # px; about 1.6in on paper, so ~230ppi
FRAME_DIR = os.path.join("art", "frames")


def annotation_times(path=os.path.join(OUT, "annotation_times.tsv")):
    """(clip, index) -> seconds into master.mp4, from build.py.

    Keyed by position rather than by text: an annotation's wording changes far
    more often than its place in the clip, and a mismatch here would put the
    wrong frame beside the right words without saying so.
    """
    out = {}
    if not os.path.exists(path):
        return out
    for i, line in enumerate(open(path, encoding="utf-8")):
        if i == 0:
            continue
        bits = line.rstrip("\n").split("\t")
        if len(bits) < 3:
            continue
        try:
            out[(int(bits[0]), int(bits[1]))] = float(bits[2])
        except ValueError:
            pass
    return out


def annotation_frames(times):
    """Grab a still for each annotation. name -> path, relative to the repo.

    Same incremental trick as the posters: a sidecar records which moment each
    frame came from, so a rebuild after an edit re-grabs only what moved.
    """
    if not times:
        return {}
    if not os.path.exists(MASTER):
        print(f"  frames skipped — {MASTER} not found (run build.py)")
        return {}
    os.makedirs(FRAME_DIR, exist_ok=True)
    idx_path = os.path.join(FRAME_DIR, "index.tsv")
    have = {}
    if os.path.exists(idx_path):
        for line in open(idx_path, encoding="utf-8"):
            b = line.rstrip("\n").split("\t")
            if len(b) == 2:
                have[b[0]] = b[1]

    made, fresh = {}, 0
    for (clip, i), secs in sorted(times.items()):
        name = f"c{clip:02d}_{i:02d}"
        fn = os.path.join(FRAME_DIR, f"{name}.jpg")
        made[(clip, i)] = fn
        stamp = f"{secs:.3f}"
        if have.get(name) == stamp and os.path.exists(fn):
            continue
        r = subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-ss", stamp, "-i", MASTER,
             "-frames:v", "1", "-vf", f"scale={FRAME_W}:-2", "-q:v", "6", fn],
            capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(fn):
            made.pop((clip, i), None)
            continue
        have[name] = stamp
        fresh += 1
    with open(idx_path, "w", encoding="utf-8") as f:
        for (clip, i) in sorted(made):
            f.write(f"c{clip:02d}_{i:02d}\t{have[f'c{clip:02d}_{i:02d}']}\n")
    kb = sum(os.path.getsize(v) for v in made.values()) / 1024
    print(f"  {FRAME_DIR}/   {len(made)} frames, {kb/1024:.1f} MB "
          f"({fresh} freshly grabbed)")
    return made


def card_spans(path=os.path.join(OUT, "boundaries.tsv")):
    """[(start, end)] of the title cards inside master.mp4.

    A poster grabbed on a card is just the card's own words in small type,
    which is useless as a thumbnail and identical to every other card. The
    build already lists every segment here, cards included, so an automatic
    grab can step over them.
    """
    rows = []
    if not os.path.exists(path):
        return []
    for line in open(path, encoding="utf-8"):
        bits = line.rstrip("\n").split("\t")
        if len(bits) < 2:
            continue
        try:
            h, m, sec = bits[0].split(":")
            rows.append((int(h) * 3600 + int(m) * 60 + float(sec), bits[1]))
        except ValueError:
            continue
    out = []
    for i, (t, nm) in enumerate(rows):
        if re.search(r"_(?:end)?card\d+\.mp4$", nm):
            out.append((t, rows[i + 1][0] if i + 1 < len(rows) else t))
    return sorted(out)


def poster_plan(secs_titles, spans, thumbs, cards=()):
    """[(name, seconds)] — where each section's poster frame comes from.

    A `thumbnail:` on the clip wins. Failing that, one declared anywhere
    inside the section is used, which is how a joined clip can supply the
    poster for the chapter it continues. Failing that, a frame a little way
    in — far enough to clear a title card, not so far as to miss the point.
    """
    jobs = []
    for n, t in secs_titles:
        span = spans.get(t)
        if not span:
            continue
        st, en = span
        if n in thumbs:
            at = thumbs[n]
        else:
            inside = sorted(v for v in thumbs.values() if st <= v < en)
            if inside:
                at = inside[0]
            else:
                # What is left of the section once its cards are taken out.
                # Comparing times across two files needs slack: chapters.txt
                # is in milliseconds and boundaries.tsv in centiseconds, so a
                # chapter can begin a few thousandths before its own card.
                free, cur = [], st
                for cs, ce in cards:
                    if ce <= st or cs >= en:
                        continue
                    cs, ce = max(cs, st), min(ce, en)
                    if cs - cur > MIN_RUN:
                        free.append((cur, cs))
                    cur = max(cur, ce)
                if en - cur > MIN_RUN:
                    free.append((cur, en))
                if free:
                    fs, fe = max(free, key=lambda p: p[1] - p[0])
                else:
                    fs, fe = st, en     # a section that is nothing but a card
                at = fs + min(AUTO_LEAD, (fe - fs) * AUTO_FRAC)
        jobs.append((f"c{n}", max(0.0, min(at, en - 0.2))))
    return jobs


def video_id(url):
    """The bare id from a youtu.be/… or watch?v=… link."""
    m = re.search(r"(?:youtu\.be/|[?&]v=|/embed/)([A-Za-z0-9_-]{6,})", url or "")
    return m.group(1) if m else None


def blocks(sheet):
    doc, _ = load_sheet(sheet)
    return [b for b in doc if isinstance(b, dict) and "clip" in b]


def front(sheet):
    """The intro block, if the sheet has one. Front matter belongs with the
    content it describes, not hardcoded in here."""
    doc, _ = load_sheet(sheet)
    for b in doc:
        if isinstance(b, dict) and isinstance(b.get("intro"), dict):
            return b["intro"]
    return {}


def frac(x):
    """3.375 -> 3 3/8, for a caption a reader can hold a ruler against."""
    whole = int(x)
    rest = round((x - whole) * 8)
    if rest == 0:
        return str(whole)
    from math import gcd
    g = gcd(rest, 8)
    return f"{whole}&nbsp;{rest//g}/{8//g}"


IMG_PARA = re.compile(r'^!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)$')


def appendix_anchor(ident):
    """The id is a label — A, 1, IV — so it is slugged before it can be an
    HTML id."""
    return "appendix-" + (re.sub(r"[^a-z0-9]+", "-", str(ident).lower()).strip("-")
                          or "x")


MEDIA = ("screen", "print")
MEDIA_TAG = re.compile(r"^@(\w+)\b[ \t]*")


def for_medium(text, medium):
    """Drop the paragraphs written for the other medium.

    The web page and the printed document say slightly different things in a
    few places — a download link is useful on screen and useless on paper,
    where the same thing is a page you can already cut out. A paragraph may
    therefore open with @screen or @print, and is kept only for that one.
    Unmarked paragraphs, which is nearly all of them, appear in both.

        @screen  A printable version is available: [download it](…).
        @print   The chart is reproduced overleaf at its true size.

    Marking a paragraph is a content decision, so it lives in the sheet with
    the words rather than as a rule in here that a rewording would silently
    break.
    """
    out = []
    for para in text.split("\n\n"):
        body = para.strip()
        if not body:
            continue
        m = MEDIA_TAG.match(body)
        if m and m.group(1).lower() in MEDIA:
            if m.group(1).lower() != medium:
                continue
            body = body[m.end():]
        out.append(body)
    return "\n\n".join(out)


def pretty_url(url):
    """The address as a person would type it: no scheme, no trailing slash."""
    return re.sub(r"^https?://", "", url.strip()).rstrip("/")


def line_for_medium(text, medium):
    """The same @screen / @print markers, for a field that is ONE line.

    for_medium() above splits on blank lines, which is right for prose and
    wrong for a heading or a colophon: those are single lines, so the
    alternatives are written one per line and the matching one is taken.

        heading: |
          @screen How to use this webpage
          @print  How to use this document

    An unmarked line is used for both, which is the common case and means
    nothing had to change in the sheet when this was added. If several lines
    survive the filter the first wins, so a stray line cannot silently
    concatenate itself onto a title.
    """
    text = str(text or "")
    if "@" not in text:
        return text.strip()
    for line in text.splitlines():
        body = line.strip()
        if not body:
            continue
        m = MEDIA_TAG.match(body)
        if m and m.group(1).lower() in MEDIA:
            if m.group(1).lower() != medium:
                continue
            return body[m.end():].strip()
        return body
    return ""


def rebase_images(text, base):
    """Point an inline ![](art/x.png) at the right place for the file being
    written: the markdown copies live in different directories."""
    def fix(m):
        path, title = m.group(2), m.group(3)
        if re.match(r"^[a-z]+:", path) or not os.path.exists(path):
            return m.group(0)
        tail = f' "{title}"' if title else ""
        return f"![{m.group(1)}]({os.path.relpath(path, base)}{tail})"
    return re.sub(r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)', fix, text)


def appendices(sheet):
    """The sheet's appendix blocks, in file order.

    Each is a chapter in its own right — listed in the contents and linkable —
    but belongs to no clip and sits at no moment in the video, so it carries
    the id written after `appendix:` instead of a clip number, and no
    timecode. The id is a label, not a position: reorder the blocks and the
    ids stay put until you change them.
    """
    doc, _ = load_sheet(sheet)
    out = []
    for b in doc or []:
        if not (isinstance(b, dict) and "clip" not in b and "appendix" in b):
            continue
        ident = str(b.get("appendix", "")).strip()
        head = str(b.get("heading", "")).strip()
        text = str(b.get("text", "")).strip()
        if ident and head and text:
            out.append({"id": ident, "heading": head, "text": text,
                        "image": str(b.get("image", "")).strip(),
                        "anchor": appendix_anchor(ident)})
    return out


def render(sheet, linked, video_url, base=OUT, dl="", frames=None):
    durs = clip_durations()
    chap_at = video_chapter_starts()
    frames = frames or {}
    L = []
    add = L.append

    fm = front(sheet)
    add("# " + str(fm.get("title", "Rubrics for a Hierarchical Liturgy")))
    add("")
    if fm.get("subtitle"):
        add("*" + str(fm["subtitle"]).strip() + "*")
        add("")
    if video_url:
        add(f"[Watch the whole video]({video_url}) · "
            f"[Download PDF]({dl}printed.pdf) · "
            f"[Download Word]({dl}printed.docx)")
        add("")
    medium = "screen" if linked else "print"
    for sec in fm.get("sections") or []:
        head = line_for_medium(sec.get("heading"), medium)
        if head:
            add("## " + head)
            add("")
        add(for_medium(str(sec.get("text", "")), medium))
        add("")
    add(f"`{build_stamp()}`")
    add("")
    colo = for_medium(str(fm.get("colophon", "")), medium).replace("\n\n", " ")
    if colo:
        add(colo)
    add("")
    if not linked:
        add("<!-- printed form: convert to HTML and print from a browser, or "
            "run it through pandoc -->")
        add("")
    add("---")
    add("")

    # ── contents ──────────────────────────────────────────────────────
    sections = []
    for b in blocks(sheet):
        if b.get("skip") is True or b.get("join") is True:
            continue
        title = _first(b, "chapter", "chapters")
        if title:
            sections.append((b["clip"], str(title).strip()))

    add("## Contents")
    add("")
    for n, title in sections:
        at = chap_at.get(title)
        stamp = f" · {mmss(at)}" if at is not None else ""
        if linked:
            anchor = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            add(f"{n}. [{title}](#{anchor}){stamp}")
        else:
            add(f"{n}. {title}{stamp}")
    for ap in appendices(sheet):
        head = ap["heading"]
        if linked:
            anchor = re.sub(r"[^a-z0-9]+", "-", head.lower()).strip("-")
            add(f"{ap['id']}. [{head}](#{anchor})")
        else:
            add(f"{ap['id']}. {head}")
    add("")
    add("---")
    add("")

    # ── the body ──────────────────────────────────────────────────────
    for b in blocks(sheet):
        n = b["clip"]
        if b.get("skip") is True:
            continue
        title = _first(b, "chapter", "chapters")
        joined = b.get("join") is True

        if title and not joined:
            at = chap_at.get(str(title).strip())
            head = str(title).strip()
            if linked and video_url and at is not None:
                head = f"{head}"
            add(f"## {head}")
            add("")
            bits = [f"clip {n}"]
            if durs.get(n): bits.append(mmss(durs[n]))
            if at is not None:
                stamp = mmss(at)
                if linked and video_url:
                    sec = int(at + 0.5)
                    bits.append(
                        f"[open on YouTube at {stamp}]({video_url}&t={sec}s)"
                        if "?" in video_url else
                        f"[open on YouTube at {stamp}]({video_url}?t={sec}s)")
                else:
                    bits.append(f"{stamp} in the video")
            add(f"*{' · '.join(bits)}*")
            add("")

        # cards: the words on screen
        for c in as_list(_first(b, "cards", "card")):
            if not isinstance(c, dict):
                continue
            img = str(c.get("image", "")).strip()
            if img:
                alt = (str(c["chapter"]) if c.get("chapter")
                       else f"{title or f'clip {n}'} — plan")
                add(f"![{md_escape(alt)}]({os.path.relpath(img, base)})")
                add("")
            txt = str(c.get("text", "")).strip()
            if txt:
                for line in txt.split("\n"):
                    add(f"> {line}" if line.strip() else ">")
                add("")

        # published prose
        for note in as_list(_first(b, "notes", "note")) or (
                [_first(b, "notes", "note")] if _first(b, "notes", "note") else []):
            if isinstance(note, str) and note.strip():
                add(note.strip())
                add("")

        # the timed directions
        entries = as_list(_first(b, "annotations", "annotation"))
        anns = [e for e in entries if isinstance(e, dict) and not is_span(e)]
        if anns:
            spans = resolve(anns, durs.get(n))
            for i, ((st, _en), e) in enumerate(zip(spans, anns)):
                text = str(e.get("text", "")).strip()
                if not text:
                    continue
                role = str(e.get("role", "")).strip()
                stamp = mmss(st) if st is not None else "—"
                lead = f"**{stamp}**"
                if role:
                    lead += f" · **{role}**"
                add(lead)
                add("")
                for line in text.split("\n"):
                    add(f"  {line}" if line.strip() else "")
                add("")
                shot = frames.get((n, i))
                if shot and os.path.exists(shot):
                    add(f"![]({os.path.relpath(shot, base)})")
                    add("")

        if not joined:
            add("---" if linked else
                '<div style="page-break-after: always"></div>')
            add("")

    for ap in appendices(sheet):
        add(f"## {ap['heading']}")
        add("")
        add(f"*Appendix {ap['id']}*")
        add("")
        add(rebase_images(for_medium(ap["text"], medium), base))
        add("")
        if ap["image"] and os.path.exists(ap["image"]):
            add(f"![{md_escape(ap['heading'])}]"
                f"({os.path.relpath(ap['image'], base)})")
            add("")
        add("---" if linked else
            '<div style="page-break-after: always"></div>')
        add("")

    return "\n".join(L).rstrip() + "\n"


ROLE_TINT = {
    "FIRST DEACON":  "#e0912c",
    "SECOND DEACON": "#7aa84b",
    "DEACONS":       "#4f9d90",
    "SUBDEACONS":    "#9b74b8",
    "SUBDEACON":     "#9b74b8",
    "SERVERS":       "#7d8598",
    "SERVER":        "#7d8598",
    "PRIEST":        "#c25f63",
    "CHOIR":         "#b3893c",
}


def tint(role):
    return ROLE_TINT.get(role.split(",")[0].strip().upper(), "#8b8378")


def data_uri(path):
    """Images must travel inside the file — an artifact cannot fetch them."""
    if not os.path.exists(path):
        return None
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()


def qr_uri(url, scale=8, border=0):
    """A QR code for `url`, as an SVG data URI — or None if segno is absent.

    SVG rather than a raster: a QR is hard edges and nothing else, so it stays
    exact at whatever size the page gives it and cannot pick up resampling
    fuzz at the module boundaries, which is precisely what stops a phone
    reading one.

    Error correction M (15%). A printed rubric is handled, folded and
    photocopied, so a code that survives a little damage is worth the two
    extra modules it costs.

    border=0 — no quiet zone inside the image. The symbol still needs one,
    but the white of the page supplies it, and the stylesheet keeps at least
    four modules clear on every side. Putting it outside means the image is
    exactly the code, so a box of a given height holds ink of that height
    whatever version the symbol comes out as — which is what lets it line up
    with the still. With the quiet zone inside, the ink was 0.80in in a 0.9in
    box and looked short beside the picture.

    The QR is print-only. On screen the page has the video itself, and a
    reader can simply click.
    """
    try:
        import segno
    except ImportError:
        return None
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="svg", scale=scale,
                                    border=border, dark="#111111",
                                    light=None, xmldecl=False, svgns=True)
    return ("data:image/svg+xml;base64,"
            + base64.b64encode(buf.getvalue()).decode())


def inline_md(t, breaks=True):
    """The sheet's **bold**, *italic*, _underline_ and [links](to.pdf), as HTML.

    Links are set aside before the emphasis passes run and put back after, so
    an underscore inside a URL cannot be mistaken for an underline.

    `breaks` decides what a newline inside the text means. On a card or an
    annotation it is a line break the writer intended, and the video shows it
    that way, so it becomes <br>. In prose — the introduction, the appendices,
    the notes — a newline is only where the line happened to be wrapped in the
    editor, and turning it into <br> reproduces that wrapping on screen: a
    paragraph ends up broken mid-sentence, with the last word stranded on its
    own line. There the lines are joined instead, and the paragraph reflows to
    whatever width the reader has.
    """
    t = str(t)
    if not breaks:
        t = " ".join(t.split())
    t = html.escape(t)
    links = []

    def stash(m):
        links.append((m.group(1), m.group(2)))
        return f"\x00{len(links) - 1}\x00"

    t = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", stash, t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", t)
    t = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<u>\1</u>", t)
    for i, (label, url) in enumerate(links):
        t = t.replace(f"\x00{i}\x00", f'<a href="{url}">{label}</a>')
    return t.replace("\n", "<br>")


def chapter_sections(sheet):
    """[(clip, title)] for the clips that open a chapter — the sections that
    get a heading, and so a player and a poster."""
    out = []
    for b in blocks(sheet):
        if b.get("skip") is True or b.get("join") is True:
            continue
        t = _first(b, "chapter", "chapters")
        if t:
            out.append((b["clip"], str(t).strip()))
    return out


def render_html(sheet, video_url, posters=None, medium="screen",
                frames=None, site=SITE, draft=""):
    posters = posters or {}
    frames = frames or {}
    durs, chap_at = clip_durations(), video_chapter_starts()
    spans = {t: (st, en) for t, st, en in video_chapters() if en and en > st}
    H = []
    add = H.append

    secs = chapter_sections(sheet)
    apps = appendices(sheet)

    # First, and before anything with a non-ASCII byte in it. Without this the
    # page depends on the server sending a charset: GitHub Pages does, but
    # python -m http.server sends a bare `text/html`, and the browser then
    # falls back to Windows-1252 and every em dash renders as â€”. The same
    # applies to anyone who saves the page and opens it from disk.
    add('<meta charset="utf-8">')
    add('<meta name="viewport" content="width=device-width, initial-scale=1">')
    add('<title>Serving a Hierarchical Liturgy</title>')
    add('<link rel="preconnect" href="https://fonts.googleapis.com">')
    add('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')
    add('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
        'family=Cormorant+Garamond:wght@500;600&family=IBM+Plex+Mono:wght@400;500'
        '&display=swap">')
    add("<style>" + CSS + "</style>")

    # A draft watermark, print and screen alike.
    #
    # In print this is ONE element: WeasyPrint repeats a position:fixed box on
    # every page, so there is nothing to place per page and nothing to get out
    # of step with the pagination.
    #
    # It sits BEHIND the content and very light, which is not only taste: the
    # QR codes carry no white backdrop of their own — the page's white is
    # their quiet zone — so ink laid across them eats into it. Light enough
    # binarises as white and the codes still read. Verified by decoding every
    # code with the watermark on; if this colour is ever darkened, decode them
    # again.
    if draft:
        add(f'<div class="watermark" aria-hidden="true">'
            f'{html.escape(draft)}</div>')

    add('<header class="masthead">')
    fm = front(sheet)
    if fm.get("subtitle"):
        add(f'  <p class="eyebrow">{html.escape(str(fm["subtitle"]).strip())}</p>')
    add("  <h1>" + html.escape(str(fm.get(
        "title", "Rubrics for a Hierarchical Liturgy"))) + "</h1>")
    if video_url:
        add('  <p class="actions">'
            f'<a href="{html.escape(video_url)}">Watch the whole video</a>'
            '<a href="printed.pdf">Download PDF</a>'
            '<a href="printed.docx">Download Word</a></p>')
    # On paper the masthead's links are dead text, and a reader holding only
    # the printed copy has no way to reach the online one. This code is the
    # route. It is NOT one of the section codes: it plays nothing, it opens
    # the document — so it is captioned and placed differently on purpose,
    # or it would be read as "this section's video".
    if medium == "print":
        home = qr_uri(site)
        if home:
            add('  <div class="homeqr">')
            add(f'    <img src="{home}" alt="QR code linking to this '
                f'document online">')
            # The address in words as well as in code. A QR is
            # useless to anyone without a phone to hand, and someone
            # reading a printed page may simply want to type it.
            add('    <p>Scan, or go to<br>'
                f'<b>{html.escape(pretty_url(site))}</b></p>')
            add('  </div>')
    add(f'  <p class="build">{html.escape(build_stamp())}</p>')
    # The colophon is CONTENT, so it lives in the sheet with the words it
    # describes rather than as a string in here that a rewording cannot reach.
    colo = for_medium(str(fm.get("colophon", "")), medium)
    if colo.strip():
        add('  <p class="colophon">'
            + inline_md(colo.replace("\n\n", " ").strip(), breaks=False)
            + '</p>')
    add("</header>")

    for sec in fm.get("sections") or []:
        add('<section class="intro">')
        head = line_for_medium(sec.get("heading"), medium)
        if head:
            add(f'  <h2>{html.escape(head)}</h2>')
        for para in for_medium(str(sec.get("text", "")), medium).split("\n\n"):
            if para.strip():
                add(f"  <p>{inline_md(para.strip(), breaks=False)}</p>")
        add("</section>")

    add('<nav class="toc" aria-label="Contents"><h2>Contents</h2><ol>')
    for n, t in secs:
        at = chap_at.get(t)
        stamp = (f'<span class="tc">{mmss(at)}</span>' if at is not None else "")
        add(f'  <li><span class="num">{n}</span>'
            f'<a href="#c{n}">{html.escape(t)}</a>{stamp}</li>')
    # In print the appendices get a list of their own, starting a page. The
    # clip list runs to 34 rows and was spilling a single appendix line onto
    # a third page by itself, which reads as a mistake. On screen it stays one
    # list — there are no pages there for a line to be stranded on.
    if medium == "print":
        add("</ol></nav>")
        add('<nav class="toc toc-appendix" aria-label="Appendices">'
            '<h2>Appendices</h2><ol>')
    for ap in apps:
        add(f'  <li><span class="num">{html.escape(ap["id"])}</span>'
            f'<a href="#{ap["anchor"]}">{html.escape(ap["heading"])}</a></li>')
    # the cut-outs are gathered at the end, so they belong in the contents —
    # only in print, since on screen each is a download beside its description
    if medium == "print" and any(
            re.search(r'\]\([^)]*"card[^"]*"\)', a["text"]) for a in apps):
        add('  <li><span class="num">&#9986;</span>'
            '<a href="#cutouts">Pages to Cut Out</a></li>')
    add("</ol></nav>")

    open_sec = False
    for b in blocks(sheet):
        n = b["clip"]
        if b.get("skip") is True:
            continue
        title = _first(b, "chapter", "chapters")
        joined = b.get("join") is True

        if title and not joined:
            t = str(title).strip()
            at = chap_at.get(t)
            if open_sec:
                add("</section>")
            add(f'<section class="chapter" id="c{n}">')
            open_sec = True
            vid = video_id(video_url)
            span = spans.get(t)
            # In print the player and the poster are both hidden, and
            # rubric_print.md is built with links off — so on paper there has
            # been no way to reach the video at all. The same still the web
            # page uses, with a QR beside it, is that way: the picture says
            # "this is a video", the code is how a phone opens it, and the two
            # together need no caption to be understood.
            #
            # The still is deliberately NOT the section's first cue frame —
            # posters are chosen a third of the way in, stepping over cards —
            # so it adds a picture rather than repeating the one below it.
            if medium == "print" and vid and span:
                # NOT a YouTube link. A printed sheet cannot be recalled, and
                # a YouTube id is not ours to keep: the service will not let a
                # video's file be replaced, so any re-upload mints a new id
                # and every sheet already printed becomes wrong. §14 records
                # that happening once already.
                #
                # Pointing at our own page makes the paper durable — the page
                # is regenerated with whatever id is current, so a re-upload,
                # or a decision to publish the clips separately, or a move off
                # YouTube entirely, is absorbed without reprinting anything.
                #
                # It also fixes the reason this came up: a bare YouTube link
                # only starts, it never stops, and the section runs on into
                # the next. The page already solves that with END_GUARD.
                #
                # The fragment is kept alongside ?play= so that with no
                # JavaScript the reader still lands on the right section.
                url = f"{site}?play=c{n}#c{n}"
                qr = qr_uri(url)
                still = posters.get(f"c{n}") if posters else None
                if qr:
                    add('  <div class="vcard">')
                    if still:
                        add(f'    <img class="vstill" src="{still}" alt="">')
                    add(f'    <img class="vqr" src="{qr}" alt="QR code '
                        f'linking to this section of the video">')
                    add('    <p class="vcap">Scan to watch</p>')
                    add('  </div>')

            add(f'  <h2>{html.escape(t)}</h2>')
            meta = [f"clip {n}"]
            if durs.get(n):
                meta.append(mmss(durs[n]))
            if at is not None:
                stamp = mmss(at)
                meta.append(f"{stamp} in the video")
            add('  <p class="meta">' + " &middot; ".join(meta) + "</p>")

            vid = video_id(video_url)
            span = spans.get(t)

            if vid and span:
                st_i, en_i = int(span[0] + 0.5), int(span[1] + 0.5)
                # A placeholder, not an iframe: the IFrame API builds the
                # player here when it scrolls into view. Adopting an existing
                # lazy-loaded iframe is unreliable, and YouTube's own `end`
                # cannot be trusted — see END_GUARD.
                src = posters.get(f"c{n}")
                data = (f'data-vid="{vid}" data-start="{st_i}" '
                        f'data-end="{en_i}"')
                nos = (f'<noscript><a href="https://www.youtube.com/watch?v='
                       f'{vid}&amp;t={st_i}s">Watch this section</a></noscript>')
                if src:
                    # A still from this very moment, not an iframe: nothing is
                    # fetched from YouTube until the reader asks for it, and
                    # every section looks like itself rather than like the
                    # one thumbnail the whole video shares.
                    add(f'  <div class="player">'
                        f'<button type="button" class="poster" {data} '
                        f'aria-label="Play this section">'
                        f'<img src="{src}" alt="" loading="lazy" '
                        f'width="{POSTER_W}" height="{round(POSTER_W*9/16)}">'
                        f'<span class="play" aria-hidden="true"></span>'
                        f'</button>{nos}</div>'
                        f'<div class="pctl"><button type="button" '
                        f'class="reset" hidden>&#8634; Back to the start'
                        f'</button></div>')
                else:
                    add(f'  <div class="player"><div class="slot" {data}>'
                        f'</div>{nos}</div>')

        if not open_sec:
            add('<section class="preamble">')
            open_sec = True

        for c in as_list(_first(b, "cards", "card")):
            if not isinstance(c, dict):
                continue
            img = str(c.get("image", "")).strip()
            if img:
                uri = data_uri(img)
                if uri:
                    alt = (str(c["chapter"]) if c.get("chapter")
                           else f"{title or f'clip {n}'} — plan")
                    add(f'  <figure><img src="{uri}" alt="{html.escape(alt)}">'
                        f'</figure>')
            txt = str(c.get("text", "")).strip()
            if txt:
                add('  <blockquote class="card"><p class="onscreen">on screen</p>'
                    + f"<p>{inline_md(txt)}</p></blockquote>")

        note = _first(b, "notes", "note")
        for item in (note if isinstance(note, list) else [note] if note else []):
            if str(item).strip():
                add(f'  <p class="note">'
                    f'{inline_md(str(item).strip(), breaks=False)}</p>')

        entries = as_list(_first(b, "annotations", "annotation"))
        anns = [e for e in entries if isinstance(e, dict) and not is_span(e)]
        if anns:
            add('  <ol class="cues">')
            for i, ((st, _e), e) in enumerate(zip(resolve(anns, durs.get(n)),
                                                  anns)):
                text = str(e.get("text", "")).strip()
                if not text:
                    continue
                role = str(e.get("role", "")).strip()
                shot = frames.get((n, i))
                add(f'    <li{" class=\"shot\"" if shot else ""}>')
                add(f'      <span class="tc">{mmss(st) if st is not None else "&mdash;"}</span>')
                add('      <div class="cue">')
                if role:
                    add(f'        <span class="role" style="--tint:{tint(role)}">'
                        f'{html.escape(role)}</span>')
                add(f'        <p>{inline_md(text)}</p>')
                add("      </div>")
                if shot:
                    uri = data_uri(shot)
                    if uri:
                        add(f'      <img class="frame" src="{uri}" alt="">')
                add("    </li>")
            add("  </ol>")

    if open_sec:
        add("</section>")

    plates = []          # (title, data uri, width, height) — printed at the end
    for ap in apps:
        add(f'<section class="chapter appendix" id="{ap["anchor"]}">')
        add(f'  <h2>{html.escape(ap["heading"])}</h2>')
        add(f'  <p class="meta">appendix {html.escape(ap["id"])}</p>')
        for para in for_medium(ap["text"], medium).split("\n\n"):
            para = para.strip()
            if not para:
                continue
            # An image on a line of its own is placed where it is written,
            # which is the only way to get it next to the sentence that
            # introduces it. The image: key still hangs one off the end.
            m = IMG_PARA.match(" ".join(para.split()))
            if m:
                uri = data_uri(m.group(2))
                if uri:
                    # `"card"` after the path means: on paper this is a thing
                    # to cut out, so print it at its true size on a page of
                    # its own, with the back of that sheet left blank.
                    # `"card"` — or `"card 7.25x5.875"` for something other
                    # than the 3 3/8 x 5 1/4 in service-book card. The size is
                    # the CUT size, and the caption states it, so a reader can
                    # check the print came out true before taking scissors to
                    # it.
                    t3 = (m.group(3) or "").strip().lower()
                    card = t3.startswith("card")
                    if card:
                        # Gathered, not printed here. A plate set beside the
                        # paragraph that describes it scatters the cut-outs
                        # through the appendices, and every appendix added
                        # later scatters them further. They are collected at
                        # the end of the document instead, so the scissors
                        # come out once.
                        dims = re.match(r"card\s+([\d.]+)\s*x\s*([\d.]+)", t3)
                        cw, ch = ((float(dims.group(1)), float(dims.group(2)))
                                  if dims else (3.375, 5.25))
                        if medium == "print":
                            plates.append((m.group(1), uri, cw, ch))
                        else:
                            # on screen there is nothing to cut out: the image
                            # is just an illustration, and each has its own
                            # download beside the words that describe it
                            add(f'  <figure><img src="{uri}" '
                                f'alt="{html.escape(m.group(1))}"></figure>')
                    else:
                        add(f'  <figure><img src="{uri}" '
                            f'alt="{html.escape(m.group(1))}"></figure>')
                continue
            add(f"  <p>{inline_md(para, breaks=False)}</p>")
        if ap["image"]:
            uri = data_uri(ap["image"])
            if uri:
                add(f'  <figure><img src="{uri}" '
                    f'alt="{html.escape(ap["heading"])}"></figure>')
        add("</section>")

    if plates:
        add('<section class="chapter plates" id="cutouts">')
        add('  <h2>Pages to Cut Out</h2>')
        add('  <p class="meta">every sheet in this document, at its true size</p>')
        add('  <p>Each is printed at the size it should be cut to. Print this '
            'document at <strong>100 percent</strong> &mdash; not "fit to '
            'page", which shrinks it just enough to be wrong &mdash; and cut '
            'on the dashed line. Where a sheet spans two facing pages, fold it '
            'down the middle into the gutter. Paste the blank side over the '
            'page it replaces.</p>')
        for title, uri, cw, ch in plates:
            fold = ' data-fold="1"' if cw > 5 else ""
            add(f'  <figure class="cardfig"><div class="cut"{fold} '
                f'style="width:{cw*72:.1f}pt;height:{ch*72:.1f}pt">'
                f'<img src="{uri}" alt="{html.escape(title)}">'
                f'</div><figcaption>{html.escape(title)} &mdash; cut on the '
                f'dashed line, {frac(cw)} &times; {frac(ch)} in'
                f'{", and fold down the middle" if fold else ""}.'
                f'</figcaption></figure>')
        add("</section>")

    if video_id(video_url):
        add(END_GUARD)

    return "\n".join(H) + "\n"


END_GUARD = """
<script>
/* Posters are stills; the real player is built on click. Nothing is fetched
   from YouTube until then — not even the API — so a page of 34 sections costs
   34 small images instead of 34 embedded players.

   At the end of a section the player is destroyed and the poster put back,
   rather than left paused on its last frame. A paused player resumes where it
   stopped, which for a bounded section means it would run on into the next
   one; rebuilding from the poster always re-applies `start`.

   The callback has to exist before the API script is inserted, or the API
   fires it into nothing and no player is ever built. */
(function () {
  var pending = [], ready = false, asked = false;

  window.onYouTubeIframeAPIReady = function () {
    ready = true;
    pending.splice(0).forEach(function (j) { build(j[0], j[1], j[2]); });
  };

  function api() {
    if (asked) return;
    asked = true;
    var s = document.createElement("script");
    s.src = "https://www.youtube.com/iframe_api";
    document.head.appendChild(s);
  }

  /* Put the still back where the player was. The button is the very node that
     was taken out, so its click handler is still on it. Everything left in
     the frame is cleared first: destroy() removes the iframe, but a reset
     pressed before the API arrived has only a placeholder to clear. */
  function restore(player, ctx) {
    if (!ctx || ctx.gone) return;
    ctx.gone = true;
    if (ctx.reset) ctx.reset.hidden = true;
    try { if (player) player.destroy(); } catch (e) {}
    while (ctx.box.firstChild) ctx.box.removeChild(ctx.box.firstChild);
    ctx.box.appendChild(ctx.btn);
    if (ctx.theatre) theatre(false, ctx);
  }

  /* Theatre: the player fills the screen, and the page waits behind it.
     Done in CSS rather than through the Fullscreen API, which needs a user
     gesture — and arriving from a scanned code is a navigation, not a tap, so
     requestFullscreen() would simply be refused. On iOS it does not apply to
     an iframe at all. A fixed overlay needs no permission and behaves the
     same everywhere.

     The reader can still reach TRUE fullscreen from the player's own button,
     because that is a tap. */
  function theatre(on, ctx) {
    var box = ctx.box;
    document.documentElement.classList.toggle("theatre-on", on);
    box.classList.toggle("theatre", on);
    if (on) {
      if (!ctx.close) {
        var b = document.createElement("button");
        b.type = "button";
        b.className = "tclose";
        b.setAttribute("aria-label", "Close the video and read the section");
        b.innerHTML = "&#10005;";
        b.onclick = function () { restore(ctx.player, ctx); };
        ctx.close = b;
      }
      box.appendChild(ctx.close);
    } else {
      if (ctx.close && ctx.close.parentNode) {
        ctx.close.parentNode.removeChild(ctx.close);
      }
      /* the section the reader scanned, now that the video has finished or
         been dismissed — they land on its text rather than wherever the page
         happened to be scrolled */
      var sec = box.closest ? box.closest(".chapter") : null;
      if (sec && sec.scrollIntoView) sec.scrollIntoView();
    }
  }

  function build(box, auto, ctx) {
    if (ctx && ctx.gone) return;    /* reset pressed while the API loaded */
    var end = parseFloat(box.getAttribute("data-end"));
    box.textContent = "";
    var player = new YT.Player(box, {
      videoId: box.getAttribute("data-vid"),
      playerVars: {
        start: parseInt(box.getAttribute("data-start"), 10),
        end: parseInt(end, 10),
        autoplay: auto ? 1 : 0,
        /* inline only in theatre, where our own overlay is already filling
           the screen; left alone elsewhere so a click in the page behaves
           exactly as it always has */
        playsinline: (ctx && ctx.theatre) ? 1 : 0,
        rel: 0
      },
      events: {
        onStateChange: function (ev) {
          /* the whole video ran out — the last section can end this way */
          if (ev.data === YT.PlayerState.ENDED) {
            restore(ev.target, ctx);
            return;
          }
          if (ev.data !== YT.PlayerState.PLAYING) return;
          /* YouTube honours `end` erratically, so stop it here too. */
          var tick = setInterval(function () {
            var t = ev.target.getCurrentTime && ev.target.getCurrentTime();
            if (typeof t === "number" && t >= end) {
              clearInterval(tick);
              try { ev.target.pauseVideo(); } catch (e) {}
              /* a beat, so the picture stops before the still replaces it */
              setTimeout(function () { restore(ev.target, ctx); }, 180);
            }
          }, 200);
        }
      }
    });
    if (ctx) ctx.player = player;
  }

  function queue(box, auto, ctx) {
    if (ready) { build(box, auto, ctx); }
    else { pending.push([box, auto, ctx]); api(); }
  }

  /* YT.Player replaces the element it is handed, so give it a throwaway div
     rather than the button, whose parent carries the aspect ratio. */
  function swap(btn, asTheatre) {
    var box = btn.parentNode;
    var slot = document.createElement("div");
    slot.className = "slot";
    ["vid", "start", "end"].forEach(function (k) {
      slot.setAttribute("data-" + k, btn.getAttribute("data-" + k));
    });
    box.replaceChild(slot, btn);

    var row = box.nextElementSibling;
    var reset = row && row.classList.contains("pctl")
      ? row.querySelector(".reset") : null;
    var ctx = { box: box, btn: btn, reset: reset, player: null, gone: false,
                theatre: !!asTheatre, close: null };
    if (reset) {
      reset.hidden = false;
      reset.onclick = function () { restore(ctx.player, ctx); };
    }
    box.__ctx = ctx;
    if (ctx.theatre) theatre(true, ctx);
    queue(slot, true, ctx);
  }

  document.querySelectorAll(".player > .poster").forEach(function (btn) {
    btn.addEventListener("click", function () { swap(btn); });
  });

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    var box = document.querySelector(".player.theatre");
    if (box && box.__ctx) restore(box.__ctx.player, box.__ctx);
  });

  /* ?play=c26 — how a printed QR code arrives.
     The sheets point here rather than at YouTube so that a re-upload, or
     publishing the clips separately, never invalidates paper already printed;
     the cost is that the page has to do what the link asks on arrival.

     Scroll first, then start that section, so the reader sees the section
     they scanned rather than the top of a very long page. Whether it then
     plays by itself is the browser's decision — a scan is a navigation, not a
     tap, so a phone may refuse to autoplay. If it does refuse, the player is
     built and sitting at the right second and one tap runs it, which is the
     same behaviour the page has always had. Nothing breaks either way.

     The id is checked against the DOM before use: it comes from a URL, and a
     mistyped or stale one should do nothing rather than throw. */
  (function () {
    var m = /[?&]play=([A-Za-z0-9_-]{1,32})/.exec(window.location.search);
    if (!m) return;
    var sec = document.getElementById(m[1]);
    if (!sec || !sec.classList.contains("chapter")) return;
    var btn = sec.querySelector(".player > .poster");
    if (!btn) return;
    if (sec.scrollIntoView) sec.scrollIntoView();
    /* after the scroll has settled, and after the poster image has had a
       moment, so the swap does not fight the browser's own anchor handling */
    setTimeout(function () { swap(btn, true); }, 260);
  })();

  /* No poster (no master.mp4 when the page was built): fall back to building
     those players outright, so the page still works. */
  document.querySelectorAll(".player > .slot[data-vid]").forEach(function (b) {
    queue(b, false, null);
  });
})();
</script>
"""

CSS = """
:root{
  --ground:#faf7f0; --panel:#f4efe4; --ink:#23201a; --muted:#6f6a5f;
  --gold:#9c7518; --rule:#e0d7c6; --quote:#efe8d9;
}
:root:not([data-theme="light"]){ }
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --ground:#12100e; --panel:#1a1713; --ink:#e8e2d6; --muted:#968d7e;
    --gold:#d9b45b; --rule:#2f2a23; --quote:#1e1a15;
  }
}
:root[data-theme="dark"]{
  --ground:#12100e; --panel:#1a1713; --ink:#e8e2d6; --muted:#968d7e;
  --gold:#d9b45b; --rule:#2f2a23; --quote:#1e1a15;
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--ground); color:var(--ink);
  font:400 17px/1.62 Georgia,"Times New Roman",serif;
  padding:0 1.5rem 6rem;
}
.masthead,.toc,.chapter{max-width:44rem;margin:0 auto}
.masthead{padding:4.5rem 0 2rem;border-bottom:1px solid var(--rule)}
.eyebrow{
  margin:0 0 .6rem; font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:.74rem; letter-spacing:.18em; text-transform:uppercase;
  color:var(--gold);
}
h1{
  margin:0; font-family:"Cormorant Garamond",Georgia,serif; font-weight:600;
  font-size:clamp(2.6rem,6vw,3.9rem); line-height:1.04; text-wrap:balance;
  letter-spacing:-.01em;
}
.standfirst{color:var(--ink);max-width:34rem;margin:1.2rem 0 0;font-size:1.12rem}
.build{
  margin:1.1rem 0 0; color:var(--gold);
  font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:.72rem; letter-spacing:.1em; text-transform:uppercase;
}
.colophon{
  color:var(--muted); max-width:34rem; margin:1rem 0 0;
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.76rem;
  line-height:1.7; letter-spacing:.02em;
}
.actions{display:flex;flex-wrap:wrap;gap:.5rem;margin:1.4rem 0 0}
.actions a{
  display:inline-block; padding:.42rem .85rem; border:1px solid var(--rule);
  border-radius:2px; color:var(--ink); text-decoration:none;
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.74rem;
  letter-spacing:.06em;
}
.actions a:hover{border-color:var(--gold);color:var(--gold)}
.intro{max-width:44rem;margin:0 auto;padding:2.2rem 0 0}
.intro h2{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.74rem;
  letter-spacing:.18em; text-transform:uppercase; color:var(--gold);
  font-weight:500; margin:0 0 .7rem;
}
.intro p{margin:0 0 .9rem}
.toc{padding:2.5rem 0 1rem}
.toc h2{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.74rem;
  letter-spacing:.18em; text-transform:uppercase; color:var(--muted);
  font-weight:500; margin:0 0 1rem;
}
.toc ol{list-style:none;margin:0;padding:0;display:grid;gap:.1rem}
.toc li{display:grid;grid-template-columns:2.2rem 1fr auto;align-items:baseline;
  gap:.5rem;padding:.3rem 0;border-bottom:1px solid transparent}
.toc li:hover{border-bottom-color:var(--rule)}
.num{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.8rem;
  color:var(--muted); font-variant-numeric:tabular-nums;
}
.toc a{color:var(--ink);text-decoration:none}
.toc a:hover{color:var(--gold)}
.preamble{max-width:44rem;margin:0 auto;padding:1.5rem 0 0}
.chapter{padding:3.2rem 0 1rem;border-top:1px solid var(--rule);margin-top:2.6rem}
.chapter h2{
  font-family:"Cormorant Garamond",Georgia,serif; font-weight:600;
  font-size:clamp(1.9rem,4vw,2.5rem); line-height:1.12; margin:0;
  text-wrap:balance;
}
.meta{
  margin:.55rem 0 1.6rem; color:var(--muted);
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.76rem;
  letter-spacing:.05em; font-variant-numeric:tabular-nums;
}
.meta a{color:var(--gold)}
blockquote.card{
  margin:0 0 1.6rem; padding:1.15rem 1.35rem; background:var(--quote);
  border-left:3px solid var(--gold); border-radius:2px;
}
blockquote.card p{margin:0}
.onscreen{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.66rem;
  letter-spacing:.16em; text-transform:uppercase; color:var(--muted);
  margin:0 0 .5rem !important;
}
.note{color:var(--muted);margin:0 0 1.5rem}
.watermark{
  position:fixed; z-index:0; pointer-events:none; user-select:none;
  top:50%; left:50%; transform:translate(-50%,-50%) rotate(-45deg);
  font-family:"Cormorant Garamond",Georgia,serif;
  font-size:8rem; letter-spacing:.22em; line-height:1;
  color:rgba(120,110,95,.13); white-space:nowrap;
}
/* the page's own content sits above it */
.masthead,.toc,.intro,.chapter{ position:relative; z-index:1 }

/* Theatre — how a section looks when the page was opened by a scanned code.
   The player is taken out of the flow and fills the viewport; the page waits
   behind it. dvh rather than vh so a phone's collapsing address bar does not
   leave a strip of page showing along the bottom. */
html.theatre-on{ overflow:hidden }
.player.theatre{
  /* Sized by the insets alone — NOT by 100vw/100dvh. The viewport units
     bought nothing and cost correctness: with width and height both set,
     the box is over-constrained against inset:0, and anywhere dvh resolves
     to zero the overlay collapses to nothing and the page appears blank.
     It did exactly that. inset:0 on a fixed box already means "the viewport",
     and it tracks a phone's collapsing address bar without help.
     width/height:auto are here only to beat .player{width:100%}. */
  position:fixed; inset:0; z-index:9999;
  width:auto; height:auto; max-width:none;
  aspect-ratio:auto; border:0; border-radius:0; background:#000;
  margin:0;
}
.player.theatre iframe{ width:100%; height:100% }
.tclose{
  position:absolute; top:max(.6rem, env(safe-area-inset-top)); right:.6rem;
  z-index:1; width:2.4rem; height:2.4rem; border-radius:50%;
  border:0; background:rgba(0,0,0,.55); color:#fff; font-size:1.1rem;
  line-height:1; cursor:pointer;
}
.tclose:focus-visible{ outline:2px solid #fff; outline-offset:2px }
@media (prefers-reduced-motion:no-preference){
  .player.theatre{ animation:theatrein .18s ease-out }
  @keyframes theatrein{ from{ opacity:0 } to{ opacity:1 } }
}

.player{
  position:relative; width:100%; aspect-ratio:16/9; margin:0;
  border:1px solid var(--rule); border-radius:3px; overflow:hidden;
  background:#000;
}
.player iframe{position:absolute;inset:0;width:100%;height:100%;border:0}
.player .slot{position:absolute;inset:0}
.player .poster{
  position:absolute;inset:0;display:block;width:100%;height:100%;
  padding:0;border:0;background:#000;cursor:pointer;
}
.player .poster img{
  width:100%;height:100%;object-fit:cover;display:block;opacity:.85;
  transition:opacity .18s ease;
}
.player .poster:hover img,.player .poster:focus-visible img{opacity:1}
.player .poster:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
.player .play{
  position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);
  width:4rem;height:4rem;border-radius:50%;display:grid;place-items:center;
  background:rgba(12,10,8,.6);border:1px solid rgba(255,255,255,.55);
  transition:background .18s ease,transform .18s ease;
}
.player .play::after{
  content:"";width:0;height:0;margin-left:.3rem;
  border-left:1rem solid #fff;
  border-top:.6rem solid transparent;border-bottom:.6rem solid transparent;
}
.player .poster:hover .play{
  background:var(--gold);transform:translate(-50%,-50%) scale(1.06);
}
@media (prefers-reduced-motion:reduce){
  .player .poster img,.player .play{transition:none}
}
/* The row is always here, occupying its height whether the button shows or
   not, so starting a section does not shove the page around. */
.pctl{min-height:1.6rem;margin:.55rem 0 1.5rem;display:flex}
/* This has to read as a control. In muted grey on a hairline --rule border
   it did not: the frame came out at 1.33:1 against the page, so all a reader
   saw was a scrap of small grey text under the video, and it was reported
   missing when it was in fact right there. The accent colour carries it. */
.reset{
  font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:.68rem;letter-spacing:.1em;text-transform:uppercase;
  color:var(--gold);background:none;border:1px solid var(--gold);
  border-radius:2px;padding:.34rem .8rem;cursor:pointer;
  transition:color .15s ease,background .15s ease;
}
.reset:hover{color:var(--ground);background:var(--gold)}
.reset:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
.appendix p{margin:0 0 1rem;max-width:38rem}
/* An appendix image is an illustration beside the prose, not the document.
   The roles chart is a tall, narrow table: at full column width it towers
   over everything around it, and the detail belongs in the card PDF anyway.
   Widen this if a future appendix wants a diagram to fill the column. */
.appendix figure,.plates figure{max-width:20rem;margin:0 auto 1.8rem}
.appendix figcaption{display:none}
.appendix p.meta{margin-bottom:1.4rem}
.player noscript a{position:absolute;inset:0;display:grid;place-items:center;
  color:var(--gold);font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:.8rem;letter-spacing:.05em}
figure{margin:0 0 1.6rem;overflow-x:auto}
figure img{width:100%;height:auto;display:block;border:1px solid var(--rule);border-radius:3px}
ol.cues{list-style:none;margin:0;padding:0;display:grid;gap:1.35rem}
ol.cues li{display:grid;grid-template-columns:4.2rem 1fr;gap:1rem;align-items:baseline}
/* a cue with its frame: the picture is a third column, small and to the side,
   so the page still holds several cues and the eye stays on the words */
ol.cues li.shot{grid-template-columns:4.2rem 1fr 1.6in}
ol.cues li.shot .frame{
  width:1.6in;height:auto;border:1px solid var(--rule);border-radius:2px;
  align-self:start;
}
.tc{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.82rem;
  color:var(--muted); font-variant-numeric:tabular-nums; letter-spacing:.02em;
}
.cue p{margin:.15rem 0 0}
.role{
  display:inline-block; font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:.66rem; letter-spacing:.14em; text-transform:uppercase;
  color:var(--tint); border:1px solid var(--tint); border-radius:2px;
  padding:.1rem .42rem; opacity:.95;
}
u{text-decoration:underline;text-underline-offset:.18em}
a:focus-visible,li:focus-visible{outline:2px solid var(--gold);outline-offset:3px}
@media (max-width:640px){
  ol.cues li{grid-template-columns:1fr;gap:.2rem}
  .toc li{grid-template-columns:2rem 1fr;}
  .toc li .tc{grid-column:2}
}
@media print{
  /* US Letter, said out loud. WeasyPrint defaults to A4, and a US printer
     asked to fit A4 onto Letter scales it by about 94% — which would leave
     the cut-out card the wrong size, silently, which is the whole point of
     it being a card. */
  @page{ size:letter; margin:16mm 15mm; }
  /* Any page the pagination leaves empty says so, rather than looking like a
     printing fault. This covers the back of the card's sheet and the filler
     that appears when the text before it happens to end on a front page. */
  @page :blank{
    @top-center{
      content:"This page is left intentionally blank.";
      font-family:"IBM Plex Mono",ui-monospace,monospace;
      font-size:8pt; color:#999;
    }
  }
  body{background:#fff;color:#000;font-size:10.5pt;line-height:1.5;padding:0}
  .masthead{padding:0 0 1.2rem;border-bottom:1px solid #bbb}
  .masthead,.toc,.chapter{max-width:none}
  h1{font-size:26pt}
  .eyebrow,.onscreen{color:#555}
  .standfirst,.colophon,.note,.meta{color:#222}
  .actions{display:none}
  .intro{max-width:none;padding:1.4rem 0 0}
  .intro h2{color:#555}
  .toc{padding-top:1.2rem}
  /* rows only. On the whole nav this forbids the list splitting at all, so
     a 34-row contents was shoved off page 1 entirely to look for a page it
     could fit on. */
  .toc li{break-inside:avoid; page-break-inside:avoid}
  /* the appendices open a page; the section list therefore does not need a
     break after it, and forcing one would leave an empty page between them */
  .toc-appendix{page-break-before:always}
  .toc-appendix + *{page-break-before:always}
  .toc li:hover{border-bottom-color:transparent}
  .preamble{max-width:none;padding:0 0 1rem}
  /* the opening card should not strand itself on a page of its own */
  .preamble + .chapter{page-break-before:avoid}
  .chapter{page-break-before:always;border-top:0;margin-top:0;padding:0 0 1rem}
  .chapter h2{font-size:16pt;break-after:avoid}
  .meta{break-after:avoid}
  a{color:#000;text-decoration:none}
  /* never split a direction, a card or a plan across a page */
  ol.cues li,blockquote.card,figure{break-inside:avoid;page-break-inside:avoid}
  blockquote.card{background:#f1f1f1;border-left-color:#777}
  .role{color:#000;border-color:#777}
  .tc{color:#333}
  figure img{border:1px solid #999}
  .player,.pctl{display:none}
  /* On paper the mark has to survive a photocopier without fogging the text
     or the codes. Grey rather than a colour, and light. */
  .watermark{
    font-size:130pt; color:rgba(0,0,0,.07); letter-spacing:.18em;
  }

  /* The video card: the section's own still, with a QR beside it. It floats
     into the space to the right of the heading, which is empty on paper, so
     it costs no vertical room and the cue frames below keep their column.
     shape-outside is not needed — the heading and the ON SCREEN card are both
     block boxes that simply narrow beside it. */
  .vcard{
    float:right; width:2.7in; margin:0 0 .5rem .6rem;
    display:flex; flex-wrap:wrap; gap:.14in; align-items:flex-start;
    break-inside:avoid; page-break-inside:avoid;
  }
  /* The still and the code are set to ONE height and sit on a common top
     edge. The posters are exactly 16:9, so 0.9in high makes the still 1.6in
     wide, and 1.6 + gap + 0.9 keeps the pair inside the 2.7in float — wide
     enough to leave a long chapter title room to set beside it.
     box-sizing so the still's 1px border is inside the 0.9in and the two
     boxes really are the same height, not the same height plus a border. */
  .vcard .vstill{
    width:1.6in; height:0.9in; box-sizing:border-box; object-fit:cover;
    border:1px solid #999; display:block;
  }
  /* No border and no background behind the code. The quiet zone is part of
     the symbol, and here the white of the page supplies it; a frame drawn
     tight against the modules is a common reason a phone will not read one. */
  .vcard .vqr{ width:0.9in; height:0.9in; display:block }
  /* The quiet zone, supplied by the page. At 0.9in over 33 modules a module
     is 0.027in, so four modules is 0.11in — the gap to the still is 0.14in,
     the page margin is clear to the right, and this keeps the caption far
     enough below. */
  .vcard .vcap{ margin-top:0.14in }
  .vcard .vcap{
    flex-basis:100%; margin:.18rem 0 0; font-size:7.6pt; color:#555;
    text-align:right;
    font-family:"IBM Plex Mono",ui-monospace,monospace; letter-spacing:.02em;
  }
  /* A float narrows the LINES beside it, not the block box — so the grey
     ON SCREEN card ran its background underneath the still, and the cue text
     ran under the caption. Only the heading and its meta line, which are
     plain text, may sit alongside; everything with a background or a frame
     column of its own clears it. */
  .chapter blockquote.card,.chapter ol.cues,.chapter figure{clear:right}

  /* The masthead code. Deliberately unlike the section cards: no still
     beside it, and a caption that says it opens the document rather than
     plays anything. */
  .masthead{ position:relative }
  .homeqr{ float:right; width:1.5in; margin:0 0 .5rem .6rem; text-align:center }
  .homeqr img{ width:1.1in; height:1.1in; display:block; margin:0 auto }
  .homeqr p{
    margin:.14in 0 0; font-size:7.6pt; color:#555; line-height:1.35;
    font-family:"IBM Plex Mono",ui-monospace,monospace; letter-spacing:.02em;
  }
  .masthead h1,.masthead .eyebrow,.masthead .colophon,.masthead .build{
    max-width:5.2in;
  }

  /* A card is printed to be cut out, so it gets a sheet to itself: the chart
     at its true size inside the cut line, and the back of that sheet blank,
     so removing it takes nothing else with it.
       break-before:right  starts it on a front (odd) page
       the blank page then falls on the back of that same sheet
       break-after:right   returns the text to the next front page  */
  /* break-before:right puts the card on a front (odd) page; break-after:right
     sends the text that follows to the NEXT front page, which leaves the back
     of the card's own sheet empty. Both together are what make the sheet
     removable: chart on one side, nothing on the other. */
  /* Scoped to figure.cardfig wherever it sits — it used to say
     `.appendix figure.cardfig`, and when the plates were gathered into their
     own section the rule stopped matching. They then packed one per page with
     no blank backs, so cutting a plate out would have punched a hole in the
     plate on the other side of the same sheet. */
  figure.cardfig{
    max-width:none; margin:0;
    break-before:right; page-break-before:right;
    break-after:right;  page-break-after:right;
  }
  /* the size comes from the sheet — see the `card` image title */
  .cardfig .cut{
    border:.7pt dashed #888; margin:1.5rem auto 0;
    display:flex; align-items:center; justify-content:center;
    position:relative;
  }
  /* a spread wide enough to need folding gets its fold line */
  .cardfig .cut[data-fold]::after{
    content:""; position:absolute; left:50%; top:0; bottom:0;
    border-left:.4pt dashed #bbb;
  }
  /* fitted inside the cut line with a 4pt margin, exactly as roles_card.pdf
     does it, and by max-* so the aspect ratio is the image's own */
  .cardfig .cut img{max-width:100%; max-height:100%; width:auto;
                    height:auto; border:0}
  .cardfig figcaption{
    display:block; text-align:center; margin:.7rem auto 0;
    font-family:"IBM Plex Mono",ui-monospace,monospace;
    font-size:8pt; color:#555;
  }
}
"""


def for_github(sheet, video_url, posters=None, draft=""):
    """Copies meant to be committed: GitHub renders the markdown in the repo,
    and Pages serves the HTML from docs/."""
    md = render(sheet, True, video_url, base=".", dl="docs/")
    with open("RUBRIC.md", "w", encoding="utf-8") as f:
        f.write(md)
    print(f"  RUBRIC.md   {len(md.splitlines())} lines   (GitHub renders this)")

    os.makedirs("docs", exist_ok=True)
    # Pages serves docs/, so anything an appendix links to has to be there.
    for src, name, what in (
            (os.path.join("art", "roles_card.pdf"), "roles_card.pdf",
             "print and cut"),
            (os.path.join("booklet", "insert_136.pdf"), "insert_136_137.pdf",
             "print, cut and paste in"),
            (os.path.join("booklet", "insert_56.pdf"), "page_56.pdf",
             "the completion of the vesting"),
            (os.path.join("booklet", "insert_64.pdf"), "pages_64_65.pdf",
             "the entrance prayers"),
            # the standalone greeting label is superseded by the 64-65 spread,
            # which carries the same text in its place in the rite. Still
            # copied, so a link already handed out does not break.
            (os.path.join("booklet", "label_is_polla.pdf"),
             "label_is_polla.pdf", "superseded by the 64-65 spread")):
        if os.path.exists(src):
            shutil.copy2(src, os.path.join("docs", name))
            print(f"  docs/{name}   "
                  f"{os.path.getsize(src) / 1024:.0f} KB   ({what})")
    doc = render_html(sheet, video_url, posters, draft=draft)
    with open(os.path.join("docs", "index.html"), "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"  docs/index.html   {len(doc) / 1024:.0f} KB   (GitHub Pages)")


def convert(dest="docs"):
    """PDF and Word, when the tools for them are on the machine.

    `dest` is where the finished files are copied for serving. They are built
    in output/, which git ignores, and copied into docs/ so the site — and a
    local server pointed at docs/ — can reach them.
    """
    made = []

    if shutil.which("weasyprint"):
        pdf = os.path.join(OUT, "printed.pdf")
        # --encoding matters: without it the em dashes come out as mojibake
        r = subprocess.run(["weasyprint", "--encoding", "utf-8",
                            os.path.join(OUT, "rubric.html"), pdf],
                           capture_output=True, text=True)
        if r.returncode == 0 and os.path.exists(pdf):
            made.append(pdf)
        else:
            print("  weasyprint failed:", (r.stderr or "").strip()[:120])
    else:
        print("  rubric.pdf skipped — brew install weasyprint")

    if shutil.which("pandoc"):
        # run from output/ so the ../art/ image paths resolve
        r = subprocess.run(["pandoc", "rubric_print.md", "-o", "printed.docx"],
                           cwd=OUT, capture_output=True, text=True)
        docx = os.path.join(OUT, "printed.docx")
        if r.returncode == 0 and os.path.exists(docx):
            made.append(docx)
        else:
            print("  pandoc failed:", (r.stderr or "").strip()[:120])
    else:
        print("  rubric.docx skipped — brew install pandoc")

    # Pages serves docs/, so the download links only work if the files are
    # there — output/ is ignored by git and never reaches the site.
    for f in made:
        print(f"  {f}   {os.path.getsize(f) / 1024:.0f} KB")
        if os.path.isdir(dest):
            shutil.copy2(f, os.path.join(dest, os.path.basename(f)))
            print(f"    -> {dest}/{os.path.basename(f)}")


def main():
    ap = argparse.ArgumentParser(description="Build the written rubric.")
    ap.add_argument("--sheet", default=default_sheet(),
                    help="the edit sheet: the annotations/ directory, "
                         "or a single .yaml file")
    ap.add_argument("--video", default="", metavar="URL",
                    help="video URL; chapter timecodes become links to it")
    ap.add_argument("--site", default=SITE, metavar="URL",
                    help="the published page; the printed QR codes point "
                         "here, not at YouTube")
    ap.add_argument("--draft", nargs="?", const="DRAFT", default="",
                    metavar="TEXT",
                    help="watermark every page (default DRAFT). A flag, not "
                         "a default, so neither a watermarked final nor an "
                         "unmarked draft can happen by accident.")
    ap.add_argument("--no-frames", action="store_true",
                    help="leave the video frames out of the PDF")
    a = ap.parse_args()

    if not os.path.exists(a.sheet):
        sys.exit(f"ERROR: {a.sheet} not found")
    os.makedirs(OUT, exist_ok=True)

    # One poster plan, shared by every copy of the page.
    spans = {t: (st, en) for t, st, en in video_chapters() if en and en > st}
    jobs = poster_plan(chapter_sections(a.sheet), spans,
                       declared_thumbnails(), card_spans())

    for linked, name in ((True, "rubric_online.md"), (False, "rubric_print.md")):
        text = render(a.sheet, linked, a.video)
        path = os.path.join(OUT, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"  {path}   {len(text.splitlines())} lines, "
              f"{len(text.split())} words")

    docs_posters = poster_frames(jobs, "docs")
    for_github(a.sheet, a.video, docs_posters, draft=a.draft)

    # output/ sits beside docs/, so the print copy points at the same posters
    # rather than keeping a second set of them.
    # output/rubric.html is what weasyprint turns into the PDF, so it is the
    # printed document, not a second copy of the web page. The PDF carries the
    # video frame beside each cue; the Word file does not, and neither does the
    # web page, which has the video itself. An annotation can opt out with
    # `frame: no` where the picture adds nothing to the words.
    frames = {} if a.no_frames else annotation_frames(annotation_times())
    doc = render_html(a.sheet, a.video,
                      {k: "../docs/" + v for k, v in docs_posters.items()},
                      medium="print", frames=frames, site=a.site,
                      draft=a.draft)
    path = os.path.join(OUT, "rubric.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"  {path}   {len(doc) / 1024:.0f} KB (images embedded)")
    convert()


if __name__ == "__main__":
    main()
