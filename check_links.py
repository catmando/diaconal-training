#!/usr/bin/env python3
"""Prove that a change to the sheet did not move a link someone already has.

The rubric page is public and the links in it have been handed out. Every
section carries three separately breakable addresses:

    #c26                     the HTML anchor  — the CLIP number, not a position
    #the-great-entrance      the Markdown anchor in RUBRIC.md — the TITLE, slugged
    data-start / data-end    where the player starts and stops, in seconds

Only the first is naturally stable. The second is the title text, so rewording
a chapter title silently retires an anchor. The third comes from
output/chapters.txt, which moves whenever anything ahead of it changes
duration — a card added or resized, a cut or speed span edited, a clip
skipped. None of that looks different from a wording change in `git diff` of
the sheet, and §8b of CLAUDE.md is the standing reminder that when this goes
wrong it goes wrong quietly: the build prints a plausible total and the wrong
times reach the page.

So: bless the state that was published, and before publishing again, diff
against it.

    python3 check_links.py              # what moved since the last publish?
    python3 check_links.py --live       # ...and does the baseline match the
                                        #    site as actually served?
    python3 check_links.py --bless      # record the current state as published

Exit status is 0 when nothing an outstanding link depends on has moved, and 1
when something has — so it can gate a publish.

Blessing is a deliberate act, done AFTER a successful publish, and
`published_links.tsv` is committed so the baseline travels with the repo
rather than living on one laptop.

This script only reads build products. It never rebuilds and never writes to
output/.
"""

import argparse, os, re, sys, urllib.request

from build import default_sheet
from make_document import blocks, video_chapters, _first, mmss

BASELINE = "published_links.tsv"
SITE = "https://catmando.github.io/hierarchical-liturgy-deacon-training/"

# The page rounds to whole seconds before writing data-start/data-end, so a
# sub-second drift that rounds to the same integer genuinely changes nothing
# for a reader. Compare what the page compares.
def whole(x):
    return int(x + 0.5)


def slug(title):
    """The Markdown anchor, exactly as make_document.py forms it."""
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def sections(sheet=None):
    """[(clip, title, start, end)] for the sections a reader can link to.

    Built the way make_document.py builds them, from the same two sources: the
    sheet decides which clips open a section, chapters.txt decides when. A
    clip that is skipped, joined, or carries no `chapter:` has no anchor of
    its own and so nothing to break.
    """
    spans = {t: (st, en) for t, st, en in video_chapters()}
    out, seen = [], {}
    for b in blocks(sheet or default_sheet()):
        if b.get("skip") is True or b.get("join") is True:
            continue
        title = _first(b, "chapter", "chapters")
        if not title:
            continue
        t = str(title).strip()
        st, en = spans.get(t, (None, None))
        out.append((b["clip"], t, st, en))
        seen.setdefault(t, []).append(b["clip"])
    dupes = {t: c for t, c in seen.items() if len(c) > 1}
    return out, dupes


def write_baseline(rows, path=BASELINE):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# Chapter addresses as last PUBLISHED. Written by "
                 "check_links.py --bless.\n")
        fh.write("# Regenerating the document must not change these, or links "
                 "already handed out move.\n")
        fh.write("clip\tstart\tend\tanchor\ttitle\n")
        for clip, title, st, en in rows:
            fh.write("%s\t%s\t%s\t%s\t%s\n" % (
                clip,
                "" if st is None else whole(st),
                "" if en is None else whole(en),
                slug(title), title))


def read_baseline(path=BASELINE):
    if not os.path.exists(path):
        return None
    rows = []
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line or line.startswith("#") or line.startswith("clip\t"):
            continue
        clip, st, en, _anchor, title = line.split("\t", 4)
        rows.append((int(clip),
                     title,
                     int(st) if st else None,
                     int(en) if en else None))
    return rows


def compare(old, new):
    """Report every difference that an outstanding link would feel."""
    problems, notes = [], []
    o = {c: (t, st, en) for c, t, st, en in old}
    n = {c: (t, st, en) for c, t, st, en in new}

    for clip in sorted(set(o) - set(n)):
        problems.append("clip %d: section GONE — #c%d is now a dead anchor "
                        "(was %r)" % (clip, clip, o[clip][0]))
    for clip in sorted(set(n) - set(o)):
        notes.append("clip %d: new section %r at %s — no link can point at it "
                     "yet" % (clip, n[clip][0], mmss(n[clip][1] or 0)))

    for clip in sorted(set(o) & set(n)):
        ot, ost, oen = o[clip]
        nt, nst, nen = n[clip]
        nst = None if nst is None else whole(nst)
        nen = None if nen is None else whole(nen)
        if ot != nt:
            problems.append(
                "clip %d: TITLE changed, so the Markdown anchor moved\n"
                "        was  %r  -> #%s\n"
                "        now  %r  -> #%s" % (clip, ot, slug(ot), nt, slug(nt)))
        if nst is None:
            problems.append("clip %d: %r has no chapter time — it is not in "
                            "output/chapters.txt at all" % (clip, nt))
        elif ost != nst:
            problems.append("clip %d: START moved %s -> %s (%+d s) — %r"
                            % (clip, mmss(ost), mmss(nst), nst - ost, nt))
        elif oen != nen and nen is not None and oen is not None:
            notes.append("clip %d: end moved %s -> %s (%+d s) — the section "
                         "plays longer or shorter, but starts where it did"
                         % (clip, mmss(oen), mmss(nen), nen - oen))
    return problems, notes


def live_rows(url=SITE):
    """What the site is actually serving, read out of the published HTML.

    HEAD is only what was last committed; §14 of CLAUDE.md is emphatic that a
    restore is verified against the live site, not against HEAD.
    """
    req = urllib.request.Request(url + "?cb=check_links",
                                 headers={"Cache-Control": "no-cache"})
    page = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    rows = []
    for m in re.finditer(
            r'<section class="chapter" id="c(\d+)">\s*<h2>(.*?)</h2>(.*?)'
            r'(?=<section |</body)', page, re.S):
        clip, title, body = int(m.group(1)), m.group(2), m.group(3)
        st = re.search(r'data-start="(\d+)"', body)
        en = re.search(r'data-end="(\d+)"', body)
        title = re.sub(r"<[^>]+>", "", title)
        title = (title.replace("&amp;", "&").replace("&lt;", "<")
                      .replace("&gt;", ">").replace("&#39;", "'")
                      .replace("&quot;", '"').replace("&middot;", "·")
                      .strip())
        rows.append((clip, title,
                     int(st.group(1)) if st else None,
                     int(en.group(1)) if en else None))
    return rows


def main():
    ap = argparse.ArgumentParser(
        description="Check that published links still point where they did.")
    ap.add_argument("--bless", action="store_true",
                    help="record the current state as published (do this "
                         "AFTER a successful publish)")
    ap.add_argument("--live", action="store_true",
                    help="also compare the baseline against the site as "
                         "actually served")
    ap.add_argument("--sheet", help="sheet file or directory")
    ap.add_argument("--url", default=SITE, help="the published page")
    ap.add_argument("--baseline", default=BASELINE,
                    help="compare against this snapshot instead of %s"
                         % BASELINE)
    args = ap.parse_args()

    if not os.path.exists(os.path.join("output", "chapters.txt")):
        sys.exit("output/chapters.txt is missing — run build.py first.")

    rows, dupes = sections(args.sheet)
    if not rows:
        sys.exit("no chapters found — is the sheet readable?")

    for title, clips in sorted(dupes.items()):
        print("WARNING  two sections share the title %r (clips %s). The page "
              "looks its times up BY TITLE, so both get the first one's."
              % (title, ", ".join(str(c) for c in clips)))

    if args.bless:
        write_baseline(rows, args.baseline)
        print("blessed %d sections into %s" % (len(rows), args.baseline))
        print("Commit it with the publish, so the baseline and the site agree.")
        return 0

    old = read_baseline(args.baseline)
    if old is None:
        sys.exit("no %s yet. If the site is currently correct, run "
                 "--bless to record it." % args.baseline)

    status = 0
    problems, notes = compare(old, rows)
    print("== the sheet and this build, against %s ==" % args.baseline)
    for p in problems:
        print("MOVED    " + p)
    for n in notes:
        print("note     " + n)
    if not problems:
        print("OK       all %d published links still land where they did."
              % len(old))
    else:
        status = 1

    if args.live:
        print()
        print("== %s ==" % args.url)
        try:
            served = live_rows(args.url)
        except Exception as e:
            print("could not read the live page: %s" % e)
            return status or 1
        if not served:
            print("no sections parsed from the live page — has its markup "
                  "changed? This check reads id=\"cN\", <h2> and data-start.")
            return status or 1
        lp, ln = compare(old, served)
        for p in lp:
            print("DRIFT    " + p)
        for n in ln:
            print("note     " + n)
        if not lp:
            print("OK       the live site matches the baseline (%d sections)."
                  % len(served))
        else:
            print("The baseline does not describe what is being served. "
                  "Trust the site, not HEAD.")
            status = 1

    return status


if __name__ == "__main__":
    sys.exit(main())
