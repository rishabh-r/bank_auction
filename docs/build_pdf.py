"""Convert the project markdown docs to PDF via headless Chrome."""

import pathlib
import subprocess
import sys
import tempfile

import markdown

DOCS = pathlib.Path(__file__).parent
CHROME = pathlib.Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe")

CSS = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm; }
body {
  font-family: "Segoe UI", "Calibri", "Noto Sans", sans-serif;
  font-size: 10.5pt; line-height: 1.55; color: #1a1a1a; margin: 0;
}
h1 {
  font-size: 20pt; color: #0b3d6b; border-bottom: 2.5px solid #0b3d6b;
  padding-bottom: 6px; margin: 26px 0 14px; page-break-after: avoid;
}
h1:first-child { margin-top: 0; }
h2 {
  font-size: 15pt; color: #12507f; margin: 22px 0 10px;
  border-bottom: 1px solid #c9d8e4; padding-bottom: 4px; page-break-after: avoid;
}
h3 { font-size: 12pt; color: #1a1a1a; margin: 18px 0 8px; page-break-after: avoid; }
p { margin: 0 0 9px; text-align: justify; }
ul, ol { margin: 0 0 10px; padding-left: 22px; }
li { margin-bottom: 4px; }
strong { color: #0b3d6b; }
code {
  font-family: "Cascadia Mono", Consolas, monospace; font-size: 9pt;
  background: #f0f3f6; padding: 1px 4px; border-radius: 3px; color: #a5305e;
}
pre {
  background: #f7f9fb; border: 1px solid #d8e2ea; border-left: 3px solid #0b3d6b;
  border-radius: 4px; padding: 10px 12px; overflow-x: auto;
  font-size: 8.2pt; line-height: 1.38; page-break-inside: avoid;
}
pre code { background: none; padding: 0; color: #1a1a1a; font-size: 8.2pt; }
table {
  border-collapse: collapse; width: 100%; margin: 10px 0 14px;
  font-size: 9.5pt; page-break-inside: avoid;
}
th {
  background: #0b3d6b; color: #fff; text-align: left;
  padding: 6px 9px; font-weight: 600;
}
td { border: 1px solid #d3dde6; padding: 5px 9px; vertical-align: top; }
tr:nth-child(even) td { background: #f6f9fb; }
blockquote {
  border-left: 3px solid #d99a2b; background: #fdf7ec;
  margin: 12px 0; padding: 8px 14px; color: #5a4520;
}
blockquote p { margin: 0; }
hr { border: none; border-top: 1px solid #d3dde6; margin: 22px 0; }
a { color: #12507f; text-decoration: none; }
"""

TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>{title}</title>
<style>{css}</style></head><body>{body}</body></html>"""


def build(md_path: pathlib.Path) -> pathlib.Path:
    html_body = markdown.markdown(
        md_path.read_text(encoding="utf-8"),
        extensions=["tables", "fenced_code", "sane_lists", "attr_list"],
    )
    html = TEMPLATE.format(title=md_path.stem, css=CSS, body=html_body)

    tmp = pathlib.Path(tempfile.gettempdir()) / f"{md_path.stem}.html"
    tmp.write_text(html, encoding="utf-8")

    pdf_path = md_path.with_suffix(".pdf")
    subprocess.run(
        [
            str(CHROME),
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--no-pdf-header-footer",
            "--virtual-time-budget=10000",
            f"--print-to-pdf={pdf_path}",
            tmp.as_uri(),
        ],
        check=True,
        capture_output=True,
        timeout=180,
    )
    return pdf_path


if __name__ == "__main__":
    if not CHROME.exists():
        sys.exit(f"Chrome not found at {CHROME}")
    for name in ("bank-auction-portal-full.md", "bank-auction-portal-summary.md"):
        out = build(DOCS / name)
        size_kb = out.stat().st_size / 1024
        print(f"{out.name:40s} {size_kb:8.1f} KB")
