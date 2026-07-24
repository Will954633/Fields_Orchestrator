# The Fields Quarterly — Print/Web Developer Brief

## What we need
A **print-focused web developer** to translate our graphic designer's full visual system for *The Fields Quarterly* (a quarterly property market report) into clean, **print-ready HTML + CSS** that renders to PDF via headless Chrome — preserving designer intent at production fidelity.

We already produce this report end-to-end from hand-coded HTML → PDF. What we have works technically but does **not** hit the designer's quality bar. We want you to rebuild the template so it matches the designer's InDesign cover system and page styling exactly, while staying **data-driven** (we drop each quarter's data in and re-render).

## Why HTML, not an editable PDF
We generate one issue per quarter, and the data changes every time — the Conviction Index number, the commentary, the charts, the property case studies, the policy section. An HTML template lets us drop new data in and re-render in seconds; an editable PDF can't do that reliably. The final output is still a high-quality, print-ready PDF — it just comes from HTML at the last step.

## Deliverables
1. **One static HTML file** — `fields_quarterly_v5.html` — with every page as an A4 `<div class="page">` section.
2. **One PDF** — `fields_quarterly_v5.pdf` — rendered via headless Chrome at print quality.
3. Clean, **semantic HTML** with named classes (`.cover`, `.conviction-index`, `.property-story`, `.policy-timeline`, `.about-author` …) — not utility-class abstraction.
4. **CSS variables** for all design tokens (colours, fonts, spacing) at the top of the stylesheet.
5. **Self-hosted / properly-licensed web fonts** (we supply Playfair Display + Poppins); designer SVG icons embedded inline or referenced.
6. A short **README** noting any design constraints we must preserve when we parametrise (image aspect ratios, fixed text lengths, min/max content per page).

### Page styles required (data-driven — realistic placeholder content is fine)
Match the designer's **cover system** and build reusable interior styles for:
- **Front cover** — the giant Conviction-Index number, the "F"-pillar photo device (B&W duotone photography masked into staggered rounded-top shapes), masthead, issue line, index eyebrow + commentary, footer.
- **Editor's letter / market commentary** — long-form serif body, drop cap, pull quotes, signature.
- **The Conviction Index + charts pages** — giant index number + a full-width chart, suburb "badges," a data table.
- **Data table / stat blocks** — indexed prices, macro-signal table (repeating rows).
- **Policy / feature spread** — a horizontal timeline device + two-column explainer + a highlighted callout box.
- **Property story card** — photo + address + facts + sale details + analysis (repeating, 2 per page).
- **About the author** — portrait + bio + signature.
- **Back cover** — full-bleed duotone photo + statement + method text + QR + contact.

## What we provide (in this folder + the designer pack)
- `current_template_reference.html` — our existing working template (**version 1**, the Q1 2026 issue). Treat as a technical reference for "what works in headless-Chrome print," **not** a design constraint — the designer's system supersedes it.
- `sample_output_fields_quarterly_q1_2026.pdf` — the rendered output of that template, so you can see HTML → print.
- `designer_finished_art.zip` — the designer's full pack:
  - **InDesign source** — `4302 - Fields - Market Update Covers_FA.indd` + `.idml` (the cover system) and the `…Assets_FA.indd/.idml` (grid, graphs, icons).
  - **Linked assets** — `5-Fields-Icon-Copper.eps` (the Fields "F" mark), cover photography (`Gold-Coast.jpg`, `Surf.jpg`, `Apartment.jpg`), `Graphs.ai`.
  - **Icon set** — 26 SVGs (Social / Documents / Communication) under `• Icons/`.
  - **Fonts** — `PlayfairDisplay-VariableFont_wght.ttf` (+ italic) and `Poppins-Bold.ttf`. (Both are also on Google Fonts if you prefer `<link>`.)
- `designer_cover_system.pdf` — the designer's four intended covers (Q1 real, Q2–Q4 template mockups).
- `designer_design_system.pdf` — the designer's system spec: cover system, editorial grid (white outer border, generous margins, "Fields rounded corner" brand shape), branded graph library, icon set.

## The visual system — the non-negotiables (from the designer)
- **Fonts:** **Playfair Display** for display type + the giant index number; **Poppins** for uppercase, letter-spaced labels/eyebrows/masthead.
- **Palette:** birch paper `#E6DDD2`, **copper** `#B76749`, **teal** `#A0D1C9`, Fields grass `#22382C`, charcoal. (Tokens are in `current_template_reference.html` `:root` — refresh to match the designer.)
- **The Conviction Index number is the hero** of the cover and index page — very large Playfair.
- **The "F"-pillar photo device** — black-and-white duotone photography masked into the Fields "F" / staggered rounded-top shapes. This is the signature; get it right. (Note: raw CSS `mask-image` is dropped by headless-Chrome print — either pre-compose the masked image as a raster, or use SVG `<clipPath>`/`<mask>` inside an inline `<svg>`, which does survive print. Please verify in the actual PDF.)
- **Editorial grid** — white outer border, generous margins, clean rhythm, "SMARTER WITH DATA" + F-mark footer.

---

## Conventions (these matter — please follow)

### Page setup
- A4 only: `@page { size: A4; margin: 0; }`
- Wrap each page: `width: 210mm; height: 297mm`
- Use **mm or pt** for layout, not pixels. No viewport units (`vh`/`vw`) — meaningless in print.
- `page-break-after: always` to end each page; `page-break-inside: avoid` on cards/blocks that must not split.

### Backgrounds and colour
Add to `body`:
```css
-webkit-print-color-adjust: exact;
print-color-adjust: exact;
```
Without it, Chrome strips background colours/images when printing.

### Fonts
- Self-hosted `@font-face` with `.woff2` (or Google Fonts `<link>`). Specify weights explicitly (400/500/600/700/900) — Chrome won't synthesise bold/black.

### Images
- Use `<img>` with `object-fit: cover` for photos. Don't rely on CSS `background-image` for hero images that must always show — use `<img>` so they survive print.
- For the F-mask device, verify the masking technique renders in the **actual PDF**, not just the browser (see note above). Provide a raster fallback if needed.

### Headers / footers
- Don't use `position: fixed` for repeating headers/footers — headless Chrome handles it inconsistently. Put the header/footer markup **on each page container** (we repeat it via templating).

### Layout
- Flexbox / CSS Grid encouraged. `position: absolute` inside a fixed-size page wrapper works well (used heavily on the cover).

### Variable content — important
The template must **flex** with content length, because each quarter differs:
- The index number is 2–4 chars; commentary length varies; a page may carry **3 or 5** charts; there may be **4–8** property stories; the policy section length varies.
- Use `min-height` not fixed `height` where text lives. Don't hard-code line counts or list lengths.
- It's fine if a long-content version flows to a second page — we handle pagination via `page-break-inside: avoid` on each card.

### Class naming
- Clear, semantic class names (`.cover`, `.editor-letter`, `.conviction-index`, `.property-story`, `.policy-timeline`, `.macro-table`, `.about-author`, `.back-cover`). We hook our data into these.

---

## What happens after delivery
We take the static HTML + CSS, replace placeholder text with template variables (`{{ index_value }}`, `{% for story in stories %}`, etc.) and wire it into our existing render pipeline (`10_Market_Report/pipeline/`). No changes to the design or process from your end after handover.

## Questions to flag
- **Fonts** — we use Playfair Display + Poppins (both linkable via Google Fonts or supplied as `.ttf`/`.woff2`). Open to your recommendation on weights.
- **Colour palette** — current tokens in `current_template_reference.html` `:root`; align to the designer's copper/teal system.
- **The F-mask device** — please confirm your chosen technique renders in headless-Chrome PDF (this is the one thing our current template couldn't do cleanly).
- **Print bleed** — current template runs edge-to-edge with `margin: 0`. If you want proper bleed/crop marks for a print house, tell us and we'll adjust the page setup.
