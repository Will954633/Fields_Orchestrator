#!/usr/bin/env python3
"""
Convert a Markdown file to PDF using weasyprint.

Usage:
    python3 scripts/md-to-pdf.py <input.md> [output.pdf]

If output path is omitted, writes <input>.pdf next to the source.
"""

import sys
import argparse
from pathlib import Path

import markdown
from weasyprint import HTML, CSS


CSS_STYLE = """
@page {
    size: A4;
    margin: 18mm 16mm 18mm 16mm;
    @bottom-right {
        content: counter(page) " / " counter(pages);
        font-size: 9pt;
        color: #888;
    }
}
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    font-size: 10.5pt;
    line-height: 1.45;
    color: #1a1a1a;
}
h1 { font-size: 20pt; margin: 0 0 12pt 0; border-bottom: 2px solid #1a1a1a; padding-bottom: 6pt; }
h2 { font-size: 14pt; margin: 18pt 0 6pt 0; color: #1a1a1a; }
h3 { font-size: 11.5pt; margin: 12pt 0 4pt 0; color: #333; }
h4 { font-size: 10.5pt; margin: 10pt 0 4pt 0; color: #333; }
p { margin: 0 0 8pt 0; }
ul, ol { margin: 0 0 8pt 18pt; padding: 0; }
li { margin: 2pt 0; }
strong { color: #000; }
em { color: #333; }
blockquote {
    margin: 8pt 0; padding: 6pt 12pt;
    border-left: 3px solid #888; background: #f4f4f4;
    color: #444; font-style: italic;
}
hr { border: none; border-top: 1px solid #ccc; margin: 14pt 0; }
table {
    border-collapse: collapse; width: 100%;
    margin: 8pt 0; font-size: 9.5pt;
}
th, td {
    border: 1px solid #ddd; padding: 5pt 7pt; text-align: left; vertical-align: top;
}
th {
    background: #f0f0f0; font-weight: 600; color: #000;
}
tr:nth-child(even) td { background: #fafafa; }
code {
    font-family: "SF Mono", Menlo, Consolas, monospace;
    font-size: 9pt; background: #f4f4f4; padding: 1pt 4pt; border-radius: 2pt;
}
pre {
    font-family: "SF Mono", Menlo, Consolas, monospace;
    font-size: 9pt; background: #f4f4f4; padding: 8pt; border-radius: 3pt;
    overflow-x: auto; line-height: 1.35;
}
pre code { background: none; padding: 0; }
a { color: #0066cc; text-decoration: none; }
img { max-width: 100%; }
"""


def convert(md_path: Path, pdf_path: Path, extra_css: str | None = None) -> None:
    md_text = md_path.read_text(encoding="utf-8")
    html_body = markdown.markdown(
        md_text,
        extensions=["extra", "tables", "fenced_code", "codehilite", "sane_lists", "toc"],
        extension_configs={"codehilite": {"css_class": "highlight"}},
    )

    html_doc = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{md_path.stem}</title></head>
<body>{html_body}</body></html>"""

    stylesheets = [CSS(string=CSS_STYLE)]
    if extra_css:
        stylesheets.append(CSS(string=extra_css))

    HTML(string=html_doc, base_url=str(md_path.parent)).write_pdf(
        target=str(pdf_path), stylesheets=stylesheets
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Markdown → PDF via weasyprint")
    parser.add_argument("input", type=Path, help="Path to .md file")
    parser.add_argument("output", type=Path, nargs="?", help="Output .pdf path (default: <input>.pdf)")
    parser.add_argument("--css", type=Path, help="Optional extra CSS file to apply")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"ERROR: input not found: {args.input}", file=sys.stderr)
        return 1

    out = args.output or args.input.with_suffix(".pdf")
    extra = args.css.read_text(encoding="utf-8") if args.css else None

    convert(args.input, out, extra)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
