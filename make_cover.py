#!/usr/bin/env python3
"""
make_cover.py — the printed rubric's cover, as a two-page PDF for the printer.

    python3 make_cover.py                 # output/cover.pdf
    python3 make_cover.py --at 806.133    # a different frame from the video
    python3 make_cover.py --no-draft      # once the review is over

**Two pages: the front cover, and a blank one that becomes the rear cover.**
The blank page is a real page with nothing on it, not an absence — a printer
imposing a cover needs the leaf to exist.

The cover image is pulled from `output/master.mp4` at full 1920x1080 rather
than from `docs/posters/`, which are 560px wide: fine on a screen, about
86 dpi across a cover, and visibly soft in print.

The text comes from the sheet's `intro:` block, so the cover cannot end up
saying something the document inside does not.
"""

import argparse
import base64
import datetime
import html
import os
import re
import subprocess
import sys
import tempfile

from build import default_sheet
from make_document import front, SITE, qr_uri, pretty_url

OUT = "output"
MASTER = os.path.join(OUT, "master.mp4")
DEFAULT_AT = 806.133          # the wide view of the sanctuary, clip 11


def grab(at, path):
    """One frame, at full resolution, as a JPEG."""
    if not os.path.exists(MASTER):
        sys.exit(f"ERROR: {MASTER} not found — the cover image comes from it.")
    r = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error",
                        "-ss", str(at), "-i", MASTER, "-frames:v", "1",
                        "-q:v", "2", path, "-y"], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(path):
        sys.exit("  ffmpeg failed: " + (r.stderr or "")[:300])
    return path


def data_uri(path, mime="image/jpeg"):
    with open(path, "rb") as fh:
        return f"data:{mime};base64," + base64.b64encode(fh.read()).decode()


CSS = """
@page{ size: letter; margin: 0 }
html,body{ margin:0; padding:0 }
body{ font-family:"Cormorant Garamond",Garamond,Georgia,serif; color:#1b1813 }

.cover{
  width:8.5in; height:11in; position:relative; overflow:hidden;
  background:#fbf9f4;
}
/* the photograph, a band across the upper half — full bleed left and right,
   so the cover does not look like a page with a picture pasted on it */
.shot{ position:absolute; top:0; left:0; width:8.5in; height:5.1in;
       object-fit:cover; object-position:center 42%; }
/* a soft wash under the title, so type never sits on busy picture */
.shot-fade{
  position:absolute; top:3.3in; left:0; width:8.5in; height:1.85in;
  background:linear-gradient(to bottom, rgba(251,249,244,0),
             rgba(251,249,244,.75) 62%, #fbf9f4 97%);
}
.block{ position:absolute; top:5.45in; left:0.95in; right:0.95in }
.eyebrow{
  font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:9.5pt; letter-spacing:.2em; text-transform:uppercase;
  color:#8a7f6a; margin:0 0 .5rem;
}
h1{ font-size:40pt; line-height:1.06; margin:0 0 .5rem; font-weight:600 }
.sub{ font-size:16pt; color:#4a4438; margin:0 0 1.2rem; font-style:italic }
.rule{ border:0; border-top:1.2pt solid #c8b06a; width:2.2in; margin:0 0 1.1rem }
.where{ font-size:12.5pt; line-height:1.55; color:#3a3428; margin:0 }
.where b{ font-weight:600 }

.foot{
  position:absolute; left:0.95in; right:0.95in; bottom:0.85in;
  display:flex; align-items:flex-end; justify-content:space-between; gap:.5in;
}
.foot .addr{
  font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:8.5pt; color:#6f6757; line-height:1.5; margin:0;
}
.foot img{ width:0.95in; height:0.95in; display:block }

.stamp{
  position:absolute; top:0.55in; left:0.95in;
  font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:10pt; letter-spacing:.22em; color:#fff;
  background:#a3232b; padding:.28rem .7rem; border-radius:2px;
}
.watermark{
  position:absolute; top:50%; left:50%;
  transform:translate(-50%,-50%) rotate(-45deg);
  font-size:150pt; letter-spacing:.2em; color:rgba(0,0,0,.07);
  white-space:nowrap; z-index:5;
}

/* The rear cover. A real, empty leaf — a printer imposing a cover needs the
   page to exist, so it carries a hard break and nothing else. NOTHING: the
   draft watermark was landing here too, and "blank" that is 14,000 pixels of
   grey is not blank. */
.rear{ page-break-before:always; width:8.5in; height:11in; background:#fbf9f4 }
"""


def build(args):
    sheet = default_sheet()
    fm = front(sheet)
    title = str(fm.get("title", "Rubrics for a Hierarchical Liturgy")).strip()
    sub = str(fm.get("subtitle", "")).strip()

    os.makedirs(OUT, exist_ok=True)
    with tempfile.TemporaryDirectory() as t:
        shot = grab(args.at, os.path.join(t, "cover.jpg"))
        img = data_uri(shot)

    qr = qr_uri(args.site)
    stamp = ('<div class="stamp">DRAFT · FOR REVIEW</div>'
             if args.draft else "")
    # No diagonal watermark on the cover. The red badge says DRAFT without
    # ambiguity, and the diagonal ran straight through the title, which is
    # the one thing on a cover that has to read cleanly.
    mark = ""

    doc = f"""<!doctype html><meta charset="utf-8">
<title>{html.escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?\
family=Cormorant+Garamond:wght@500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>{CSS}</style>
<div class="cover">
  <img class="shot" src="{img}" alt="">
  <div class="shot-fade"></div>
  {stamp}{mark}
  <div class="block">
    <p class="eyebrow">A training guide</p>
    <h1>{html.escape(title)}</h1>
    <p class="sub">{html.escape(sub)}</p>
    <hr class="rule">
    <p class="where">
      Built on video of a hierarchical Divine Liturgy served
      <b>20 June 2026</b><br>
      at Saints Peter and Paul Church, Endicott, New York<br>
      Orthodox Church in America &middot; Diocese of New York and New Jersey
    </p>
  </div>
  <div class="foot">
    <p class="addr">The video, and this document online:<br>
      <b>{html.escape(pretty_url(args.site))}</b></p>
    <img src="{qr}" alt="QR code to the document online">
  </div>
</div>
<div class="rear"></div>
"""
    hp = os.path.join(OUT, "cover.html")
    pp = os.path.join(OUT, "cover.pdf")
    open(hp, "w", encoding="utf-8").write(doc)
    r = subprocess.run(["weasyprint", "--encoding", "utf-8", hp, pp],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("  weasyprint failed: " + (r.stderr or "")[:400])

    pages = subprocess.run(["pdfinfo", pp], capture_output=True,
                           text=True).stdout
    n = int(re.search(r"Pages:\s+(\d+)", pages).group(1))
    print(f"  {pp}   {os.path.getsize(pp)/1024:.0f} KB   {n} pages")
    if n != 2:
        print(f"  ⚠ expected 2 pages (front cover + blank rear), got {n}")
    return pp


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--at", type=float, default=DEFAULT_AT,
                    help="seconds into master.mp4 for the cover image")
    ap.add_argument("--site", default=SITE)
    ap.add_argument("--no-draft", dest="draft", action="store_false",
                    help="drop the DRAFT marks, once the review is over")
    ap.add_argument("--open", dest="open_", action="store_true")
    args = ap.parse_args()
    pdf = build(args)
    if args.open_:
        subprocess.run(["open", pdf])
    return 0


if __name__ == "__main__":
    sys.exit(main())
