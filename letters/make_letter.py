#!/usr/bin/env python3
"""
make_letter.py — the reviewer letter, as a one-page PDF.

    python3 letters/make_letter.py                    # one proof copy
    python3 letters/make_letter.py --names names.txt  # one PDF per name
    python3 letters/make_letter.py --open             # open it when done

The letter is `letters/letter.md`. Three placeholders are filled in:

    {title-and-name}   one per line of --names; without it, a visible marker
                       so a proof reads as a proof and cannot be posted by
                       mistake
    {qr}               generated from the URL found in the letter itself, so
                       the code and the printed address cannot disagree
    {signature}        --signature FILE, scaled to a sensible width
    {date}             optional. Without it the date is set at the top right,
                       where a formal letter carries it. Generated at build
                       time, so a reprint cannot go out under a stale date;
                       --date fixes it to the day of posting instead.

**One page is a requirement**, so the script measures the result and says so.
If it overruns, --leading and --size tighten it rather than anyone editing
the prose to fit.

Nothing here is committed: the letter carries a personal phone number and the
repository is public. See .gitignore.
"""

import argparse
import base64
import datetime
import html
import io
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LETTER = os.path.join(HERE, "letter.md")

# One page is the requirement, so the script fits the type to the words
# rather than asking anyone to fit the words to the type. Each rung is a
# little tighter than the last; the first that comes out on one page wins.
# Nothing below 10pt — this goes to clergy who may not thank us for 9pt.
#
#   size   leading  gap   qr
LADDER = [("10.5", "1.32", "0.6",  "1.05"),
          ("10.5", "1.28", "0.52", "0.95"),
          ("10.5", "1.25", "0.48", "0.90"),
          ("10",   "1.30", "0.55", "0.95"),
          ("10",   "1.26", "0.50", "0.90")]


def find_url(text):
    """The address the letter itself prints. Taking it from the prose rather
    than a constant in here is the point: the QR and the words a reader types
    are then the same thing by construction, and cannot drift apart."""
    m = re.search(r"https?://[^\s<>()\[\]*]+", text)
    return m.group(0).rstrip(".,") if m else ""


def qr_img(url, inches=1.05):
    try:
        import segno
    except ImportError:
        return '<p class="warn">[segno not installed — no QR code]</p>'
    buf = io.BytesIO()
    # border=0: the quiet zone comes from the page's white, so the box IS the
    # ink and lines up with whatever size we ask for. Same as the rubric.
    segno.make(url, error="m").save(buf, kind="svg", scale=8, border=0,
                                    dark="#111111", light=None,
                                    xmldecl=False, svgns=True)
    uri = "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()
    return (f'<img class="qr" src="{uri}" style="width:{inches}in;'
            f'height:{inches}in" alt="QR code for {html.escape(url)}">')


def sig_img(path, inches=1.9):
    if not path:
        return ""
    if not os.path.exists(path):
        sys.exit(f"ERROR: signature not found: {path}")
    mime = "image/png" if path.lower().endswith(".png") else "image/jpeg"
    with open(path, "rb") as fh:
        uri = f"data:{mime};base64," + base64.b64encode(fh.read()).decode()
    return f'<img class="sig" src="{uri}" style="width:{inches}in" alt="">'


def md_to_html(text):
    """Only what this letter uses: paragraphs, **bold**, *italic*, and a bare
    URL or mailto left as plain text — a printed letter has nothing to click,
    and an underlined blue address on paper is just noise.

    In the body a newline is only where the line was wrapped in the editor,
    so the lines are joined. **From "Yours in Christ" onward they are not**:
    a name and the church under it are deliberate lines, and joining them ran
    the whole sign-off together as one sentence.
    """
    out = []
    signoff = False
    for para in text.split("\n\n"):
        if re.match(r"^\s*Yours in Christ", para):
            signoff = True
        lines = [l.strip() for l in para.splitlines() if l.strip()]
        if not lines:
            continue
        p = "\n".join(lines) if signoff else " ".join(" ".join(lines).split())
        if p in ("{qr}", "{signature}"):      # placed by the caller
            out.append(p)
            continue
        p = html.escape(p)
        if signoff:
            p = p.replace("\n", "<br>")
        p = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", p)
        p = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", p)
        # a numbered point hangs its text off the number
        cls = ' class="item"' if re.match(r"^\d\)", p) else ""
        out.append(f"<p{cls}>{p}</p>")
    return "\n".join(out)


CSS = """
@page{ size: letter; margin: 0.9in 1in 0.8in; }
html,body{ margin:0; padding:0 }
body{
  font-family: "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif;
  font-size: %(size)spt; line-height: %(lead)s; color:#111;
}
p{ margin:0 0 %(gap)sem }
p.item{ margin-left:1.4em; text-indent:-1.4em }
strong{ font-weight:600 }
.qrline{ margin:.45em 0 .55em; text-align:center }
.qr{ display:inline-block }
.sig{ display:block; margin:.15em 0 .1em }
/* The name must never be parted from "Yours in Christ" by a page break —
   it did exactly that, landing the signature block alone on page 2. */
.signoff{ margin-top:.2em; break-inside:avoid; page-break-inside:avoid }
.signoff p{ margin:0 }
.warn{ color:#b00; font-family:monospace; font-size:9pt }
.date{ text-align:right; margin:0 0 .6em }
.proof{
  color:#b00; font-family:monospace; font-size:9pt; letter-spacing:.06em;
}
"""


def read_names(path):
    """The recipients. A .csv with a `title-and-name` column, or a plain file
    with one name per line.

    The column is found by name rather than by position, so adding an address
    column — or reordering them — cannot silently start addressing letters to
    someone's postcode.
    """
    if not os.path.exists(path):
        sys.exit(f"ERROR: {path} not found")
    if path.lower().endswith(".csv"):
        import csv
        with open(path, newline="", encoding="utf-8-sig") as fh:
            rows = list(csv.reader(fh))
        if not rows:
            sys.exit(f"ERROR: {path} is empty")
        # headers may carry stray spaces from a spreadsheet export
        head = [h.strip().lower() for h in rows[0]]
        want = ("title-and-name", "title and name", "name")
        col = next((i for i, h in enumerate(head) if h in want), None)
        if col is None:
            sys.exit(f"ERROR: {path} has no 'title-and-name' column "
                     f"(found: {', '.join(head)})")
        # A surname column, if there is one, only ever reaches the FILE NAME
        # — never the salutation, which stays exactly what the sheet says.
        # Addressing envelopes by hand means matching a letter to an envelope,
        # and three Fathers called by first name alone do not sort well.
        sur = next((i for i, h in enumerate(head)
                    if h in ("last-name", "last name", "surname")), None)
        out = []
        for r in rows[1:]:
            if len(r) > col and r[col].strip():
                last = (r[sur].strip() if sur is not None and len(r) > sur
                        else "")
                out.append((r[col].strip(), last))
        if not out:
            sys.exit(f"ERROR: {path} has a header but no rows — no one to "
                     f"write to yet.")
        return out
    return [(n.strip(), "") for n in open(path, encoding="utf-8")
            if n.strip() and not n.lstrip().startswith("#")]


def build(args, rung=None):
    if rung:
        args.size, args.leading, args.gap, args.qr = (
            rung[0], rung[1], rung[2], float(rung[3]))
    raw = open(LETTER, encoding="utf-8").read()
    url = find_url(raw)
    if not url:
        print("  ⚠ no URL found in the letter — the QR code will be skipped")

    names = read_names(args.names) if args.names else []
    if not names:
        names = [(None, "")]      # one proof copy

    os.makedirs(args.out, exist_ok=True)
    made = []
    for name, last in names:
        body = raw
        if name:
            body = body.replace("{title-and-name}", name)
        else:
            body = body.replace(
                "{title-and-name}",
                "‹title and name›")
        doc = md_to_html(body)
        doc = doc.replace(
            "{qr}",
            f'<div class="qrline">{qr_img(url, args.qr) if url else ""}</div>')
        doc = doc.replace("{signature}", sig_img(args.signature, args.sig_width))

        # Set at build time rather than typed into the markdown, so a reprint
        # weeks later cannot go out under the date the draft was written.
        # --date pins it to the day of posting when that matters more.
        when = args.date or datetime.date.today().strftime("%-d %B %Y")
        datehtml = f'<p class="date">{html.escape(when)}</p>'
        if "{date}" in doc:
            doc = doc.replace("{date}", datehtml)
        else:
            doc = datehtml + doc

        # the sign-off block is kept together so a page break cannot part the
        # signature from the name under it
        doc = re.sub(r"(<p>Yours in Christ,</p>)", r'<div class="signoff">\1',
                     doc) + "</div>"

        head = ("" if name else
                '<p class="proof">PROOF — name not yet filled in</p>')
        page = (f"<!doctype html><meta charset=\"utf-8\">"
                f"<style>{CSS % {'size': args.size, 'lead': args.leading, 'gap': args.gap}}</style>"
                f"{head}{doc}")

        stem = ("proof" if not name else
                re.sub(r"[^A-Za-z0-9]+", "_",
                       f"{last} {name}" if last else name).strip("_"))
        hp = os.path.join(args.out, f"letter_{stem}.html")
        pp = os.path.join(args.out, f"letter_{stem}.pdf")
        open(hp, "w", encoding="utf-8").write(page)
        r = subprocess.run(["weasyprint", "--encoding", "utf-8", hp, pp],
                           capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit("  weasyprint failed: " + (r.stderr or "")[:300])
        pages = page_count(pp)
        # While walking the ladder an overrun is expected and not worth
        # reporting — only the rung that works, or an explicit setting the
        # caller chose, gets a line.
        if rung is None or pages == 1:
            flag = "" if pages == 1 else f"   ⚠ {pages} PAGES"
            print(f"  {os.path.relpath(pp)}   "
                  f"{os.path.getsize(pp)/1024:.0f} KB{flag}")
            if pages != 1:
                print("    one page is the requirement — drop --size and "
                      "--leading to let it fit itself")
        made.append(pp)
    return made


def page_count(pdf):
    try:
        out = subprocess.run(["pdfinfo", pdf], capture_output=True,
                             text=True).stdout
        m = re.search(r"Pages:\s+(\d+)", out)
        return int(m.group(1)) if m else 0
    except FileNotFoundError:
        return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--names", metavar="FILE",
                    help="a .csv with a title-and-name column, or a plain "
                         "file with one name per line")
    ap.add_argument("--signature", default="", metavar="FILE",
                    help="signature image, PNG or JPEG")
    ap.add_argument("--sig-width", type=float, default=1.9, metavar="IN")
    ap.add_argument("--qr", type=float, default=1.05, metavar="IN",
                    help="QR size in inches")
    # These defaults are the ones that FIT. One page is the requirement, so
    # the plain command has to produce one; 11pt/1.38 ran to two.
    # No defaults: unset means "fit it for me", set means "use exactly this".
    ap.add_argument("--size", help="body type size in points (default: fitted)")
    ap.add_argument("--leading", help="line height (default: fitted)")
    ap.add_argument("--gap", help="paragraph spacing in em (default: fitted)")
    ap.add_argument("--date", default="", metavar="TEXT",
                    help="override the date; default is the day it is built")
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    ap.add_argument("--open", action="store_true", dest="open_",
                    help="open the result when done")
    args = ap.parse_args()

    fixed = any(v is not None for v in (args.size, args.leading, args.gap))
    if fixed:
        # an explicit setting is obeyed exactly, even if it overruns — the
        # caller is deliberately overriding the fit
        args.size = args.size or "10.5"
        args.leading = args.leading or "1.28"
        args.gap = args.gap or "0.52"
        made = build(args)
    else:
        for i, rung in enumerate(LADDER, 1):
            made = build(args, rung)
            if all(page_count(m) == 1 for m in made):
                if i > 1:
                    print(f"  (fitted on rung {i} of {len(LADDER)}: "
                          f"{rung[0]}pt / {rung[1]} leading)")
                break
        else:
            print("  \u26a0 it will not fit on one page even at the tightest "
                  "setting. The words have to come down.")
    if args.open_ and made:
        subprocess.run(["open", made[0]])
    return 0


if __name__ == "__main__":
    sys.exit(main())
