#!/usr/bin/env python3
"""
Generate Seller Book — HTML + PDF Distribution
================================================
Converts the markdown seller book draft into:
  1. A styled HTML page (for web viewing)
  2. A print-optimised PDF (for download/email)

Usage:
  python3 scripts/generate_seller_book.py
  python3 scripts/generate_seller_book.py --md-file output/seller_book_draft_v4.md
  python3 scripts/generate_seller_book.py --html-only
  python3 scripts/generate_seller_book.py --pdf-only

Output:
  output/seller_book/seller_book.html
  output/seller_book/seller_book.pdf
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader

try:
    import markdown
except ImportError:
    print("Installing markdown library...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "markdown", "-q"])
    import markdown

AEST = ZoneInfo("Australia/Brisbane")
ROOT = Path("/home/fields/Fields_Orchestrator")
TEMPLATE_DIR = ROOT / "templates"
OUTPUT_DIR = ROOT / "output" / "seller_book"
DEFAULT_MD = ROOT / "output" / "seller_book_draft_v4.md"


def parse_markdown_to_chapters(md_text: str) -> dict:
    """
    Parse the markdown book into structured chapters.
    Returns dict with title, subtitle, author, chapters list.
    """
    lines = md_text.split("\n")

    # Extract metadata from first few lines
    title = "Strategic House Price Maximisation"
    subtitle = "A Data-Driven Guide for Gold Coast Homeowners"
    author = "Will Simpson"

    # Find title
    for line in lines[:10]:
        if line.startswith("# ") and not line.startswith("## "):
            title = line.lstrip("# ").strip()
            break

    # Find subtitle
    for line in lines[:10]:
        if line.startswith("### "):
            subtitle = line.lstrip("# ").strip()
            break

    # Split into chapters by H1 headings
    chapters = []
    current_chapter = None
    current_lines = []

    # Skip front matter (everything before first H1 that isn't the title)
    front_matter_lines = []
    in_front_matter = True
    chapter_started = False
    title_seen = False

    for i, line in enumerate(lines):
        if line.startswith("# ") and not line.startswith("## "):
            heading = line.lstrip("# ").strip()

            # Skip the very first H1 (book title)
            if not title_seen:
                title_seen = True
                continue

            # Save previous chapter
            if current_chapter is not None:
                content_md = "\n".join(current_lines)
                chapters.append({
                    "id": slugify(current_chapter),
                    "title": current_chapter,
                    "content_md": content_md,
                })
                current_lines = []

            current_chapter = heading
            in_front_matter = False
            chapter_started = True

        elif in_front_matter and not chapter_started:
            front_matter_lines.append(line)
        elif current_chapter is not None:
            current_lines.append(line)

    # Don't forget the last chapter
    if current_chapter is not None and current_lines:
        chapters.append({
            "id": slugify(current_chapter),
            "title": current_chapter,
            "content_md": "\n".join(current_lines),
        })

    # Convert front matter
    front_matter_md = "\n".join(front_matter_lines)

    return {
        "title": title,
        "subtitle": subtitle,
        "author": author,
        "front_matter_md": front_matter_md,
        "chapters": chapters,
    }


def slugify(text: str) -> str:
    """Convert heading text to a URL-friendly ID."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")[:60]


def render_chapter_md(md_text: str) -> str:
    """
    Convert markdown to HTML, with special handling for:
    - [PHOTO: ...], [CHART: ...], [FIGURE: ...] markers
    - [QR CODE: ...] markers
    - Tables
    - Blockquotes
    """
    # Image mapping: marker ID -> actual image file
    IMAGE_MAP = {
        "COVER": "book-images/inside-cover.jpg",  # placeholder until UX cover
        "INSIDE-COVER": "book-images/inside-cover.jpg",
        "V-1": "book-images/will-at-desk.jpg",
        "HST-1": None,  # special: side-by-side comparison
        "CH1-2": "book-images/open-home.jpg",
        "CH1-5": "book-images/burleigh-sunrise.jpg",
        "CH2-3": "book-images/varsity-lake-cycling.jpg",
        "CH3-3": "book-images/twilight-home.jpg",
        "CH3-STUDY": "book-images/auction-study-abstract.png",
        "CH1-INLINE": "book-images/currumbin-beach-kids.jpg",
        "CH6-INLINE": "book-images/burleigh-market.jpg",
        "CH7-INLINE": "book-images/hampton-park.jpg",
        "CH4-4": "book-images/vela-224.jpg",
        "CH5-2": None,  # special: side-by-side comparison (reuse HST-1)
        "CH5-3": "book-images/outdoor-entertaining.jpg",
        "CH5-5": "book-images/backyard-golden-hour.jpg",
        "CH5-FG1": "book-images/front-garden-before.png",
        "CH5-FG2": "book-images/front-garden-after.png",
        "CH5-6": "book-images/palmer-colonial-aerial.jpg",
        "CH6-3": None,  # TBD
        "CH7-4": "book-images/lakelands-aerial.jpg",
        "CH8-2": None,  # TBD
        "CH9-1": "book-images/robina-town-centre.jpg",
        "CH9-2": "book-images/varsity-park-family.jpg",
        "CH9-3": "book-images/beach-kids.jpg",
        "AA-1": "book-images/outdoor-entertaining.jpg",  # reuse CH5-3
        "AA-2": None,  # TBD
        "ABOUT-1": "book-images/will-headshot.jpg",
        "CH4-5": "book-images/burleigh-headland-aerial.jpg",
    }

    # Chart and figure image mapping
    CHART_MAP = {
        "CH1-1": "book-images/charts/ch1-1-domain-accuracy.png",
        "CH1-4": "book-images/charts/ch1-4-price-drivers.png",
        "CH2-1": "book-images/charts/ch2-1-monthly-heatmap.png",
        "CH3-1": "book-images/charts/ch3-1-buyer-skip.png",
        "CH3-2": "book-images/charts/ch3-2-method-of-sale.png",
        "CH4-1": "book-images/charts/ch4-1-overpricing-penalty.png",
        "CH5-4": "book-images/charts/ch5-4-presale-roi.png",
        "CH6-1": "book-images/charts/ch6-1-agent-volume.png",
        "CH6-2": "book-images/charts/ch6-2-commission-comparison.png",
        "CH7-1": "book-images/charts/ch7-1-buyer-pool.png",
        "CH7-3": "book-images/charts/ch7-3-marketing-benefit.png",
        "APPX-C-1": "book-images/charts/appx-c-1-leading-lagging.png",
    }

    FIGURE_MAP = {
        "CH1-3": "book-images/charts/ch1-3-valuation-process.png",
        "CH4-2": "book-images/charts/ch4-2-pricing-conditions.png",
        "CH4-3": "book-images/charts/ch4-3-emotional-peak.png",
        "CH5-1": "book-images/charts/ch5-1-positioning-framework.png",
        "CH7-2": "book-images/charts/ch7-2-rea-comparison.png",
        "CH8-1": "book-images/charts/ch8-1-selling-timeline.png",
        "SM-1": "book-images/charts/sm-1-final-accounting.png",
    }

    # Side-by-side comparison pairs
    COMPARISON_PAIRS = {
        "HST-1": ("book-images/interior-bad.jpg", "book-images/interior-good.jpg",
                   "Poor lighting reduces buyer enquiry", "Professional photography generates 118% more online views — more viewers, more competition, higher prices (REA Group)"),
        "CH5-2": ("book-images/interior-bad.jpg", "book-images/interior-good.jpg",
                   "Poor lighting reduces buyer enquiry", "Professional photography generates 118% more online views — more viewers, more competition, higher prices (REA Group)"),
    }

    # Captions for specific images
    CAPTIONS = {
        "CH4-4": "Image: Vela, 224 Christine Avenue, Burleigh Waters. Credit: burleighconstructions.com.au",
        "INSIDE-COVER": None,
        "V-1": "Will Simpson — Founder of Fields Real Estate",
        "HST-1": None,  # handled by comparison labels
        "CH1-2": "Buyers arriving at an open home on the southern Gold Coast.",
        "CH1-5": None,  # full spread, no caption
        "CH2-3": "Robina parklands — the lifestyle that draws families to the southern Gold Coast.",
        "CH3-3": "17A Sandpiper Drive, Burleigh Waters, tested the local market with a new record listing price of $4,150,000 in March, 2026. Twilight photography and warm lighting perfectly set the tone for the property, which gathered significant interest. The property sold on the 31st of March after listing for approximately 6 weeks (sale price not disclosed).",
        "CH3-STUDY": "Frino, A., Peat, M. and Wright, D. (2012), The impact of auctions on residential property prices. Accounting & Finance, 52: 815-830.",
        "CH1-INLINE": "Currumbin Beach — the lifestyle Gold Coast families build their lives around.",
        "CH6-INLINE": "Burleigh Heads weekend markets — the rhythm of life that draws buyers to the southern Gold Coast.",
        "CH7-INLINE": "Hampton Park, Burleigh Waters — the kind of green space that anchors family life in the suburb.",
        "CH4-5": None,  # full spread, no caption
        "CH5-2": None,  # handled by comparison labels
        "CH5-3": "Covered outdoor entertaining with pool — the kind of image that stops a buyer mid-scroll.",
        "CH5-5": "North-facing backyard at golden hour. This was the lead image Sarah's agent chose over the renovated kitchen.",
        "CH5-FG1": "Midday photo with poor lighting and empty right-side garden bed.",
        "CH5-FG2": "Twilight photography with fully landscaped right-side garden bed. Notice the distinct contrast in the feel of the two images.",
        "CH5-6": None,  # full spread, no caption
        "CH7-4": None,  # full spread, no caption
        "CH9-1": "Robina Town Centre at twilight.",
        "CH9-2": "Family afternoon at a Varsity Lakes park.",
        "CH9-3": "Tallebudgera Creek, Burleigh Waters.",
        "AA-1": "Well-presented outdoor entertaining — the Gold Coast lifestyle that sells.",
        "AA-2": None,
        "ABOUT-1": None,  # About section, no caption needed
    }

    # Pre-process visual markers before markdown conversion
    # Replace [PHOTO: ID — description] with actual images or styled placeholders
    def replace_visual_marker(match):
        marker_type = match.group(1).upper()
        content = match.group(2).strip()

        # Parse ID and description
        if "\u2014" in content:
            marker_id, description = content.split("\u2014", 1)
        elif " - " in content:
            marker_id, description = content.split(" - ", 1)
        else:
            marker_id = ""
            description = content

        marker_id = marker_id.strip()
        description = description.strip()

        # Check for side-by-side comparisons
        if marker_id in COMPARISON_PAIRS:
            img1, img2, label1, label2 = COMPARISON_PAIRS[marker_id]
            return (
                f'\n<div class="image-comparison">'
                f'<div class="comparison-item">'
                f'<img src="{img1}" alt="{label1}" loading="lazy">'
                f'<span class="comparison-label">{label1}</span>'
                f'</div>'
                f'<div class="comparison-item">'
                f'<img src="{img2}" alt="{label2}" loading="lazy">'
                f'<span class="comparison-label">{label2}</span>'
                f'</div>'
                f'</div>\n'
            )

        # Check for chart/figure images
        if marker_type == "CHART" and marker_id in CHART_MAP and CHART_MAP[marker_id]:
            img_path = CHART_MAP[marker_id]
            caption_html = f'<figcaption>{description}</figcaption>' if description else ''
            return (
                f'\n<figure class="book-image book-chart">'
                f'<img src="{img_path}" alt="{description}" loading="lazy">'
                f'{caption_html}'
                f'</figure>\n'
            )

        if marker_type == "FIGURE" and marker_id in FIGURE_MAP and FIGURE_MAP[marker_id]:
            img_path = FIGURE_MAP[marker_id]
            caption_html = f'<figcaption>{description}</figcaption>' if description else ''
            return (
                f'\n<figure class="book-image book-figure">'
                f'<img src="{img_path}" alt="{description}" loading="lazy">'
                f'{caption_html}'
                f'</figure>\n'
            )

        # Check if we have an actual image for this marker
        if marker_type == "PHOTO" and marker_id in IMAGE_MAP and IMAGE_MAP[marker_id]:
            img_path = IMAGE_MAP[marker_id]
            caption = CAPTIONS.get(marker_id, description)
            is_spread = marker_id in ("INSIDE-COVER", "CH1-5", "CH4-5", "CH5-6", "CH7-4")
            is_portrait = marker_id in ("ABOUT-1",)
            is_document = marker_id in ("CH3-STUDY",)
            is_inline_right = marker_id in ("CH1-INLINE", "CH6-INLINE", "CH7-INLINE")
            if is_spread:
                css_class = "book-image spread"
            elif is_portrait:
                css_class = "book-image portrait"
            elif is_document:
                css_class = "book-image document"
            elif is_inline_right:
                css_class = "book-image inline-right"
            else:
                css_class = "book-image"
            caption_html = f'<figcaption>{caption}</figcaption>' if caption else ''
            return (
                f'\n<figure class="{css_class}">'
                f'<img src="{img_path}" alt="{description}" loading="lazy">'
                f'{caption_html}'
                f'</figure>\n'
            )

        # QR codes
        if marker_type == "QR CODE":
            return (
                f'\n<div class="qr-marker">'
                f'<div class="qr-marker-icon">QR</div>'
                f'<span class="qr-marker-text">{description}</span>'
                f'</div>\n'
            )

        # Fallback: styled placeholder for charts, figures, and unassigned photos
        type_labels = {
            "PHOTO": "\U0001f4f7 PHOTOGRAPH",
            "CHART": "\U0001f4ca DATA VISUALISATION",
            "FIGURE": "\U0001f4d0 FIGURE",
            "QR CODE": "\U0001f517 QR CODE",
        }
        label = type_labels.get(marker_type, marker_type)
        full_desc = f"{marker_id} \u2014 {description}" if marker_id and description else (marker_id or description)
        return (
            f'\n<div class="visual-marker">'
            f'<span class="visual-marker-type">{label}</span>'
            f'<span class="visual-marker-desc">{full_desc}</span>'
            f'</div>\n'
        )

    # Match [TYPE: content] patterns
    md_text = re.sub(
        r'\[(PHOTO|CHART|FIGURE|QR CODE):\s*(.+?)\]',
        replace_visual_marker,
        md_text,
        flags=re.DOTALL
    )

    # Convert horizontal rules that are just "---" to styled dividers
    md_text = re.sub(r'^---\s*$', '<hr class="chapter-divider">', md_text, flags=re.MULTILINE)

    # Convert markdown to HTML
    html = markdown.markdown(
        md_text,
        extensions=[
            "tables",
            "fenced_code",
            "nl2br",
        ]
    )

    # Post-process: style key statistics as pull quotes
    # Pattern: **bold number or stat** at start of a paragraph
    html = re.sub(
        r'<p><strong>(Domain overvalued 89%[^<]*)</strong></p>',
        r'<div class="pull-stat"><strong>\1</strong></div>',
        html
    )

    return html


def build_toc(chapters: list[dict]) -> str:
    """Build table of contents HTML from chapters list."""
    toc_html = '<nav class="toc-list">\n'
    for ch in chapters:
        toc_html += f'  <a href="#{ch["id"]}" class="toc-item">{ch["title"]}</a>\n'
    toc_html += '</nav>'
    return toc_html


def generate_html(book_data: dict, pdf_url: str = "seller_book.pdf") -> str:
    """Render the complete HTML page using Jinja2 template."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("seller_book.html")

    # Render each chapter's markdown to HTML (kept for compatibility — print template
    # now iterates over `pages` instead, but some shared helpers may still use chapters)
    rendered_chapters = []
    for ch in book_data["chapters"]:
        rendered_chapters.append({
            "id": ch["id"],
            "title": ch["title"],
            "content": render_chapter_md(ch["content_md"]),
        })

    # Render front matter
    front_matter_html = render_chapter_md(book_data.get("front_matter_md", ""))

    # Build the full pages list (same data the reader uses) so the print template
    # can render image-only pages, double-page spreads, and overlay captions.
    all_pages = build_pages(book_data)

    html = template.render(
        title=book_data["title"],
        subtitle=book_data["subtitle"],
        author=book_data["author"],
        chapters=rendered_chapters,
        pages=all_pages,
        total_pages=len(all_pages),
        front_matter=front_matter_html,
        toc=build_toc(rendered_chapters),
        generated_date=datetime.now(AEST).strftime("%B %Y"),
        pdf_url=pdf_url,
    )

    return html


def split_chapter_to_pages(chapter_html: str, chapter_title: str, chapter_id: str) -> list[dict]:
    """Split a chapter's HTML into individual pages for the reader.

    Strategy: split on <h2> and <h3> headings, and extract spread images
    as separate image pages.
    """
    pages = []

    # ── Extract full-bleed spread photos at the chapter level — they remain
    #    inline markers so they appear at the position they were placed. ──
    spread_pattern = r'<figure class="book-image spread">.*?</figure>'
    for m in re.finditer(spread_pattern, chapter_html, re.DOTALL):
        src_match = re.search(r'src="([^"]+)"', m.group(0))
        if src_match:
            chapter_html = chapter_html.replace(m.group(0), f'<!--SPREAD:{src_match.group(1)}-->', 1)

    chart_pattern = r'<figure class="book-image book-(?:chart|figure)">(.*?)</figure>'

    sections = re.split(r'(?=<h2[^>]*>)', chapter_html)

    first_chunk = True
    for i, section in enumerate(sections):
        section = section.strip()
        if not section:
            continue

        # Extract charts/figures from THIS section only — defer them so they
        # render after the section's text. This keeps text pages dense and
        # places each chart on its own page at the end of its h2 section.
        section_charts = []
        while True:
            cm = re.search(chart_pattern, section, re.DOTALL)
            if not cm:
                break
            inner = cm.group(1)
            src_match = re.search(r'src="([^"]+)"', inner)
            cap_match = re.search(r'<figcaption>(.*?)</figcaption>', inner, re.DOTALL)
            if src_match:
                section_charts.append((
                    src_match.group(1),
                    cap_match.group(1).strip() if cap_match else "",
                ))
            section = section.replace(cm.group(0), "", 1)

        # Now process the section's text + spread markers
        marker_re = r'<!--(SPREAD):([^>]+?)-->'
        tokens = re.split(marker_re, section)
        # tokens: [text, "SPREAD", src, text, "SPREAD", src, ...]

        idx_t = 0
        while idx_t < len(tokens):
            chunk = tokens[idx_t]
            _emit_content_pages(pages, chunk, chapter_id, chapter_title, first_chunk)
            if chunk and chunk.strip():
                first_chunk = False

            if idx_t + 2 < len(tokens) and tokens[idx_t + 1] == "SPREAD":
                pages.append({
                    "type": "image",
                    "content": "",
                    "image_src": tokens[idx_t + 2],
                    "id": f"{chapter_id}-spread-{len(pages)}",
                })
                idx_t += 3
            else:
                idx_t += 1

        # Emit the section's chart/figure pages AFTER its text
        for src, cap in section_charts:
            pages.append({
                "type": "chart",
                "content": "",
                "image_src": src,
                "caption": cap,
                "id": f"{chapter_id}-chart-{len(pages)}",
            })

    return pages


def _emit_content_pages(pages: list, content: str, chapter_id: str, chapter_title: str, is_first: bool) -> None:
    """Emit one or more content pages from a text chunk. Adds the chapter h1
    to the first chunk, then applies the existing h3-split + page-fill logic."""
    content = content.strip()
    if not content:
        return

    if is_first:
        content = f'<h1>{chapter_title}</h1>\n{content}'

    text_only = re.sub(r'<[^>]+>', '', content).strip()
    if len(text_only) < 10:
        return

    if len(text_only) > 2000:
        h3_parts = re.split(r'(?=<h3[^>]*>)', content)
        buffer = ""
        buffer_weight = 0
        PAGE_MAX = 1800
        IMG_WEIGHT = 1000

        def _weight(html_part: str) -> int:
            text_len = len(re.sub(r'<[^>]+>', '', html_part).strip())
            img_count = len(re.findall(r'<(img|figure)\b', html_part))
            return text_len + img_count * IMG_WEIGHT

        for h3_part in h3_parts:
            h3_part = h3_part.strip()
            h3_text = re.sub(r'<[^>]+>', '', h3_part).strip()
            if len(h3_text) < 10:
                continue
            part_weight = _weight(h3_part)
            if '<h3' not in h3_part:
                buffer = (buffer + '\n' + h3_part) if buffer else h3_part
                buffer_weight += part_weight
                continue
            if buffer and '<h3' in buffer and (buffer_weight + part_weight) > PAGE_MAX:
                pages.append({
                    "type": "content",
                    "content": buffer,
                    "image_src": None,
                    "id": f"{chapter_id}-p{len(pages)}",
                })
                buffer = h3_part
                buffer_weight = part_weight
            else:
                buffer = (buffer + '\n' + h3_part) if buffer else h3_part
                buffer_weight += part_weight
        if buffer:
            pages.append({
                "type": "content",
                "content": buffer,
                "image_src": None,
                "id": f"{chapter_id}-p{len(pages)}",
            })
    else:
        pages.append({
            "type": "content",
            "content": content,
            "image_src": None,
            "id": f"{chapter_id}-p{len(pages)}",
        })


def build_pages(book_data: dict) -> list[dict]:
    """Build the unified ordered page list used by both the web reader and the
    print/PDF template. Returns a list of page dicts with keys:
      type     — "cover" | "toc" | "image" | "content"
      id       — stable identifier
      content  — rendered HTML for content/toc pages
      image_src — path to image for image pages
      caption  — overlay caption text (image pages only)
      spread_side — "left" or "right" when a paired double-spread; absent otherwise
    """
    all_pages = []

    # Page 1: Cover
    all_pages.append({
        "type": "cover",
        "content": "",
        "image_src": None,
        "id": "cover",
    })

    # Page 2: Inside cover (full-bleed Burleigh photo) — single-page image, no split
    all_pages.append({
        "type": "image",
        "content": "",
        "image_src": "book-images/inside-cover.jpg",
        "caption": "Sunrise off Burleigh Heads. The point break behind these paddlers was declared a National Surfing Reserve in February 2012.",
        "id": "inside-cover",
    })

    # Page 3: Table of contents
    rendered_chapters = []
    for ch in book_data["chapters"]:
        rendered_chapters.append({
            "id": ch["id"],
            "title": ch["title"],
            "content": render_chapter_md(ch["content_md"]),
        })

    toc_html = '<h2 class="toc-heading">Contents</h2><ol class="toc-list">'
    for i, ch in enumerate(rendered_chapters):
        toc_html += f'<li><span class="toc-num">{i+1:02d}</span> {ch["title"]}</li>'
    toc_html += '</ol>'

    all_pages.append({
        "type": "toc",
        "content": toc_html,
        "image_src": None,
        "id": "toc",
    })

    # Double-page photo spreads inserted before specific chapters.
    # These will be marked spread_side=left/right so the print template can
    # render each half across the gutter when bound.
    SPREADS_BEFORE_CHAPTER = {
        "chapter-3-auction-or-private-treaty": "book-images/burleigh-kayaking-spread.jpg",
        "chapter-4-setting-the-right-price": "book-images/robina-town-centre-spread.jpg",
        "chapter-7-the-marketing-that-actually-matters": "book-images/cbus-spread.jpg",
    }

    # Caption overlays for full-bleed photo pages (keyed by image src)
    SPREAD_CAPTIONS = {
        "book-images/inside-cover.jpg": "Sunrise off Burleigh Heads. The point break behind these paddlers was declared a National Surfing Reserve in February 2012.",
        "book-images/burleigh-sunrise.jpg": "Rick Shores at the foot of the Burleigh Pavilions. Opened 2016 — named Best Restaurant in Queensland in the Delicious 100 and a Good Food Guide hat.",
        "book-images/burleigh-kayaking-spread.jpg": "Burleigh Beach. Fifteen minutes east of Robina, Varsity Lakes, and Burleigh Waters — and one of the most consistent right-hand point breaks in Australia.",
        "book-images/robina-town-centre-spread.jpg": "Robina Town Centre opened in 1996 — 130,000 m² of retail across 400 stores, the largest enclosed mall ever built in Australia in a single development. The suburb around it is one of the country's largest master-planned communities.",
        "book-images/burleigh-headland-aerial.jpg": "The headlands of Burleigh and North Burleigh are remnants of the Tweed Volcano — at 23 million years old, the largest erosion caldera in the Southern Hemisphere. The basalt outcrops shape every wave that runs along this coast.",
        "book-images/palmer-colonial-aerial.jpg": "Palmer Colonial in the foreground, CBUS Super Stadium and the Springbrook plateau beyond. Springbrook sits within the Gondwana Rainforests of Australia World Heritage Area — one of the most extensive subtropical rainforest systems on Earth.",
        "book-images/cbus-spread.jpg": "CBUS Super Stadium, 1 December 2024. A crowd of 25,297 watched the Matildas play Brazil — the Olympic silver medallists — at the home of the Gold Coast Titans.",
        "book-images/lakelands-aerial.jpg": "Lakelands Golf Club, Merrimac — Australia's first Jack Nicklaus Signature course, opened 17 February 1997. The Surfers Paradise skyline runs along the horizon, fifteen minutes north.",
        "book-images/burleigh-beach-spread.jpg": "South from North Burleigh — the same coastline that opened this book at sunrise.",
    }

    # Chapters: split each into pages
    for ch in rendered_chapters:
        if ch["id"] in SPREADS_BEFORE_CHAPTER:
            spread_src = SPREADS_BEFORE_CHAPTER[ch["id"]]
            spread_caption = SPREAD_CAPTIONS.get(spread_src)
            all_pages.append({
                "type": "image",
                "content": "",
                "image_src": spread_src,
                "caption": spread_caption,
                "spread_side": "left",
                "id": f"{ch['id']}-pre-spread-1",
            })
            all_pages.append({
                "type": "image",
                "content": "",
                "image_src": spread_src,
                "caption": spread_caption,
                "spread_side": "right",
                "id": f"{ch['id']}-pre-spread-2",
            })
        chapter_pages = split_chapter_to_pages(ch["content"], ch["title"], ch["id"])
        # Attach captions to any in-chapter spread image pages
        for p in chapter_pages:
            if p.get("type") == "image" and p.get("image_src") in SPREAD_CAPTIONS:
                p["caption"] = SPREAD_CAPTIONS[p["image_src"]]
        all_pages.extend(chapter_pages)

    # Closing spread — Burleigh Beach long view, true double-page bookend
    all_pages.append({
        "type": "image",
        "content": "",
        "image_src": "book-images/burleigh-beach-spread.jpg",
        "spread_side": "left",
        "id": "closing-spread-1",
    })
    all_pages.append({
        "type": "image",
        "content": "",
        "image_src": "book-images/burleigh-beach-spread.jpg",
        "spread_side": "right",
        "id": "closing-spread-2",
    })

    # Final pass: ensure every image page that has a mapped caption gets it
    for p in all_pages:
        if p.get("type") == "image" and p.get("image_src") in SPREAD_CAPTIONS and not p.get("caption"):
            p["caption"] = SPREAD_CAPTIONS[p["image_src"]]

    return all_pages


def generate_reader_html(book_data: dict, pdf_url: str = "/seller-guide.pdf") -> str:
    """Render the book as a single-page reader experience."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("seller_book_reader.html")

    all_pages = build_pages(book_data)

    html = template.render(
        title=book_data["title"],
        subtitle=book_data["subtitle"],
        author=book_data["author"],
        pages=all_pages,
        total_pages=len(all_pages),
        generated_date=datetime.now(AEST).strftime("%B %Y"),
        pdf_url=pdf_url,
    )

    return html


def html_to_pdf(html_path: str, pdf_path: str) -> bool:
    """Convert HTML to PDF using Chrome headless."""
    chrome = None
    for candidate in ["google-chrome", "chromium-browser", "chromium"]:
        try:
            subprocess.run([candidate, "--version"], capture_output=True, check=True)
            chrome = candidate
            break
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue

    if not chrome:
        print("ERROR: No Chrome/Chromium found for PDF generation")
        return False

    cmd = [
        chrome, "--headless", "--disable-gpu", "--no-sandbox",
        "--disable-software-rasterizer",
        f"--print-to-pdf={pdf_path}",
        "--print-to-pdf-no-header",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=10000",
        f"file://{html_path}"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print(f"  Chrome PDF error: {result.stderr[:500]}")
        return False

    return os.path.exists(pdf_path)


def main():
    parser = argparse.ArgumentParser(description="Generate Seller Book HTML + PDF")
    parser.add_argument("--md-file", default=str(DEFAULT_MD),
                        help="Path to markdown source file")
    parser.add_argument("--html-only", action="store_true",
                        help="Generate HTML only, skip PDF")
    parser.add_argument("--pdf-only", action="store_true",
                        help="Generate PDF only (requires existing HTML)")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR),
                        help="Output directory")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    html_path = output_dir / "seller_book.html"
    pdf_path = output_dir / "seller_book.pdf"

    if not args.pdf_only:
        # Read markdown source
        md_path = Path(args.md_file)
        if not md_path.exists():
            print(f"ERROR: Markdown file not found: {md_path}")
            sys.exit(1)

        print(f"Reading: {md_path}")
        md_text = md_path.read_text(encoding="utf-8")

        # Parse into chapters
        print("Parsing chapters...")
        book_data = parse_markdown_to_chapters(md_text)
        print(f"  Found {len(book_data['chapters'])} chapters")
        for ch in book_data["chapters"]:
            print(f"    - {ch['title']}")

        # Generate print HTML (for PDF)
        print("Generating print HTML...")
        html_content = generate_html(book_data, pdf_url="seller_book.pdf")
        html_path.write_text(html_content, encoding="utf-8")
        html_size = html_path.stat().st_size / 1024
        print(f"  Print HTML: {html_path} ({html_size:.0f} KB)")

        # Generate reader HTML (for web)
        reader_path = output_dir / "seller_book_reader.html"
        print("Generating reader HTML...")
        try:
            reader_content = generate_reader_html(book_data, pdf_url="/seller-guide.pdf")
            reader_path.write_text(reader_content, encoding="utf-8")
            reader_size = reader_path.stat().st_size / 1024
            print(f"  Reader HTML: {reader_path} ({reader_size:.0f} KB)")
        except Exception as e:
            print(f"  Reader generation failed: {e} (template may not exist yet)")

    if not args.html_only:
        if not html_path.exists():
            print(f"ERROR: HTML file not found: {html_path}")
            sys.exit(1)

        # Generate PDF
        print("Generating PDF...")
        if html_to_pdf(str(html_path.resolve()), str(pdf_path.resolve())):
            pdf_size = pdf_path.stat().st_size / 1024
            print(f"  PDF: {pdf_path} ({pdf_size:.0f} KB)")
        else:
            print("  PDF generation failed")
            sys.exit(1)

    print("\nDone!")
    print(f"  HTML: file://{html_path.resolve()}")
    if pdf_path.exists():
        print(f"  PDF:  {pdf_path.resolve()}")


if __name__ == "__main__":
    main()
