"""Turn docs/SOLUTION.md into a print-ready PDF using a local Edge/Chrome in headless mode.

    python tests/build_pdf.py --drive "https://drive.google.com/..." [--video "https://..."] [--out solution.pdf]
"""
import argparse
import html
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRIVATE = "shared privately with the submission (it contains Kuku's confidential scripts)"

CSS = """
@page { size: A4; margin: 11mm 13mm 11mm; }
:root { --ink:#1f2328; --mut:#626b75; --acc:#0e5a6b; --acc2:#e8f2f4; --line:#e4e8eb; --tint:#f5f8f9; }
body { font: 9.3pt/1.45 "Segoe UI", "Helvetica Neue", Arial, sans-serif; color: var(--ink); margin: 0; }
h1 { font-size: 21pt; font-weight: 700; letter-spacing: -0.4px; margin: 0; color: #12181d; }
p.sub { color: var(--mut); font-size: 9.8pt; margin: 1px 0 9px; }
p.sub i { font-style: normal; }
h2 { font-size: 11pt; font-weight: 650; color: var(--acc); margin: 11px 0 4px; display: flex; align-items: center; gap: 8px; }
h2::after { content: ""; flex: 1; height: 1px; background: var(--line); }
p { margin: 2px 0 5px; }
ul, ol { margin: 2px 0 5px; padding-left: 16px; }
li { margin: 2px 0; }
li::marker { color: var(--acc); }
b { font-weight: 600; }
table { border-collapse: collapse; width: 100%; margin: 5px 0 7px; font-size: 8.8pt; }
th { text-align: left; font-weight: 600; color: #fff; background: var(--acc); padding: 3.5px 8px; }
th:first-child { border-top-left-radius: 5px; } th:last-child { border-top-right-radius: 5px; }
td { padding: 3px 8px; border-bottom: 1px solid var(--line); vertical-align: top; }
tr:nth-child(odd) td { background: var(--tint); }
table { break-inside: avoid; } h2, p.keep { break-after: avoid; }
code { font: 8.3pt Consolas, monospace; background: #eef1f3; border-radius: 3px; padding: 0 3px; }
a { color: var(--acc); text-decoration: none; }
.links { display: flex; border: 1px solid var(--line); border-radius: 7px; margin: 0 0 7px; overflow: hidden; }
.links div { flex: 1; padding: 5px 10px; border-left: 1px solid var(--line); background: #fff; }
.links div:first-child { border-left: 0; }
.links span { display: block; font-size: 7.2pt; text-transform: uppercase; letter-spacing: .7px; color: var(--mut); }
.links a { font-weight: 600; font-size: 8.7pt; white-space: nowrap; }
.links div:nth-child(2) { flex: 1.45; }
.glance { display: flex; gap: 7px; margin: 0 0 4px; }
.glance div { flex: 1; background: var(--acc2); border-radius: 7px; padding: 6px 10px 6px; }
.glance b { display: block; font-size: 15pt; font-weight: 700; color: var(--acc); line-height: 1.1; }
.glance span { display: block; font-size: 7.9pt; color: #3b4650; line-height: 1.3; margin-top: 1px; }
"""


def inline(t: str) -> str:
    t = html.escape(t, quote=False)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", t)
    t = re.sub(r"(?<![\"'>=])(https?://[^\s<)·]+)", r'<a href="\1">\1</a>', t)
    return t


def links_bar(ln: str) -> str:
    cells = []
    for part in ln.split(" · "):
        m = re.match(r"\*\*(.+?):\*\*\s*(?:\(([^)]*)\):\s*)?(.*)", part.strip())
        if not m:
            continue
        label, note, val = m.group(1), m.group(2), m.group(3).strip()
        if val.startswith("http"):
            shown = re.sub(r"^https?://(www\.)?", "", val).split("?")[0].rstrip("/")
            if label.lower() == "video":
                shown = "Watch (2 min)"
            elif "drive.google.com" in shown:
                shown = "Open on Google Drive"
            body = f'<a href="{html.escape(val)}">{html.escape(shown)}</a>'
        else:
            body = html.escape(val)
        sub = f" ({html.escape(note)})" if note else ""
        cells.append(f"<div><span>{html.escape(label)}{sub}</span>{body}</div>")
    return '<div class="links">' + "".join(cells) + "</div>"


def glance_strip(ln: str) -> str:
    cells = []
    for part in ln.split(":**", 1)[1].split(" · "):
        m = re.match(r"\s*\*\*(.+?)\*\*\s*(.*)", part)
        if m:
            cells.append(f'<div><b>{html.escape(m.group(1))}</b><span>{inline(m.group(2))}</span></div>')
    return '<div class="glance">' + "".join(cells) + "</div>"


def md_to_html(md: str) -> str:
    out, lines, i = [], md.splitlines(), 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("# "):
            out.append(f"<h1>{inline(ln[2:])}</h1>")
        elif ln.startswith("## "):
            out.append(f"<h2>{inline(ln[3:])}</h2>")
        elif ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            i -= 1
            h = "".join(f"<th>{inline(c)}</th>" for c in rows[0])
            b = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
            if out and out[-1].startswith("<p>"):
                out[-1] = '<p class="keep">' + out[-1][3:]
            out.append(f"<table><tr>{h}</tr>{b}</table>")
        elif re.match(r"(\d+\.|-) ", ln):
            tag = "ol" if ln[0].isdigit() else "ul"
            items = []
            while i < len(lines) and re.match(r"(\d+\.|-) ", lines[i]):
                items.append(re.sub(r"^(\d+\.|-) ", "", lines[i]))
                i += 1
            i -= 1
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>")
        elif ln.startswith("**Live app:**"):
            out.append(links_bar(ln))
        elif ln.startswith("**At a glance:**"):
            out.append(glance_strip(ln))
        elif ln.strip():
            cls = ' class="sub"' if out and out[-1].startswith("<h1>") else ""
            out.append(f"<p{cls}>{inline(ln)}</p>")
        i += 1
    return "\n".join(out)


def browser() -> str:
    for p in [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe"]:
        if Path(p).exists():
            return p
    for n in ("msedge", "google-chrome", "chromium", "chrome"):
        if shutil.which(n):
            return shutil.which(n)
    sys.exit("Edge or Chrome not found")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drive", default="", help="Drive link to the raw outputs folder")
    ap.add_argument("--video", default="", help="walkthrough video link (optional)")
    ap.add_argument("--out", default=str(ROOT.parent / "submission" / "Promo_Finder_Solution.pdf"))
    a = ap.parse_args()
    md = (ROOT / "docs" / "SOLUTION.md").read_text(encoding="utf-8")
    if a.drive:
        md = md.replace(PRIVATE, a.drive)
    if a.video:
        md = re.sub(r"^(\*\*Live app:\*\*.*)$", lambda m: m.group(1) + f" · **Video:** {a.video}", md, count=1, flags=re.M)
    out = Path(a.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    page = out.with_suffix(".html")
    page.write_text(f"<!doctype html><html><head><meta charset='utf-8'><title>Promo Finder Solution</title>"
                    f"<style>{CSS}</style></head><body>{md_to_html(md)}</body></html>", encoding="utf-8")
    subprocess.run([browser(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={out}", page.as_uri()], check=True, capture_output=True, timeout=120)
    pages = len(re.findall(rb"/Type\s*/Page[^s]", out.read_bytes()))
    print(f"wrote {out} ({pages} page{'s' if pages != 1 else ''})")


if __name__ == "__main__":
    main()
