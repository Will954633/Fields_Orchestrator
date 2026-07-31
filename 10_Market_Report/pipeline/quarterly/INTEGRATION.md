# The Fields Quarterly — pipeline integration

The developer-delivered template is now the **canonical** report format.

- **Template:** `pipeline/quarterly/index.html` (+ `assets/fonts/`, `assets/img/`) — semantic HTML, self-hosted fonts (Playfair Display, Poppins, Source Serif Pro), 36 A4 pages.
- **Render:** `python3 pipeline/render_quarterly.py [--sync-charts | --regen-charts] --out <label>` → `issues/<label>/`.
- **Source bundle:** the developer's zip is at `assets/HTML_270726/fields-quarterly.zip`.

## What's automated vs authored
This is an **editorial** report — ~30 of the 36 pages carry quarter-specific prose (the editor's letter, the case-study narratives, per-suburb analysis). Producing a new issue is therefore **content authoring + chart regeneration**, not a find-replace. Do NOT global-replace the index value (e.g. `98.6`→`94.4`): the number is woven into Q1-specific sentences whose logic would break.

| Layer | How it updates each quarter |
|---|---|
| **Charts** (6 of 9) | Automated. `render_quarterly.py --regen-charts` re-runs `fci_calculator.py` + `generate_charts.py` and copies them into the graph slots (see CHART_MAP). |
| **3 suburb charts** (`graph_page_20/24/28`, 1280×880) | Developer-custom — **no pipeline source yet**. Either get the developer's chart source, or add matching per-suburb charts to `generate_charts.py`. |
| **Data seams** (cover number, dates, per-suburb FCI, key stats) | Edit in `index.html`. Pull values from the live pipeline (`manual_market_pulse.py --show-data`, `fci_calculator.py`). |
| **Editorial content** (~30 pages) | Authored each quarter. |

## Chart mapping (developer graph slot → our pipeline chart)
| Slot | Pipeline chart | Page |
|---|---|---|
| `graph_page_05.png` | `01_fci_main.png` | 05 — FCI line |
| `graph_page_07.png` | `02_conviction_map.png` | 07 — Conviction Map |
| `graph_page_09.png` | `03_tension.png` | 09 — price vs conviction |
| `graph_page_14.png` | `04_indexed_prices.png` | 14 — indexed price *(developer shipped `07_distributions` here — fix on next sync)* |
| `graph_page_16.png` | `05_sales_volume.png` | 16 — sales volume |
| `graph_page_17.png` | `06_dom.png` | 17 — days-on-market |
| `graph_page_20/24/28.png` | *(developer-custom suburb charts)* | 20/24/28 — Robina / BW / VL |

## 36-page content map (evergreen vs quarter-specific)
- **Evergreen** (write once, reuse): 03 how-to-read · 08 section divider · 32 how-charts-are-made · 33 what-this-doesn't-answer · 35 glossary · 36 back cover.
- **Quarter-specific** (author each issue): 01 cover (number+date) · 04 editor's letter · 05–09 the index + components + maps · 10–11 lead case study · 13–18 the data pages · 20–31 the three suburb sections + case studies · 34 reflection.

## Cover QR — tracked per issue
The cover carries a QR unique to the issue. Scanning it logs engagement before
redirecting, so we can measure readership of a specific issue of a specific
asset — across both the printed copy and the PDF.

```
pipeline/generate_issue_qr.py            asset_code = quarterly-q2-2026
   │                                          │
   ├─ upserts system_monitor.print_assets ────┘  (registry: code -> destination + issue metadata)
   └─ writes quarterly/assets/img/qr_<asset_code>.svg   (vector, grass on birch)
                     │
   QR encodes  https://vm.fieldsestate.com.au/track/a/<asset_code>
                     │  tracking-server/server.py  ->  @app.route("/a/<asset_code>")
                     ├─ INSERTS ONE DOC PER SCAN -> system_monitor.asset_scans
                     ├─ $inc print_assets.scan_count / $set last_scan_at
                     ├─ PostHog `print_asset_qr_scan` + Telegram ping
                     └─ 302 -> destination + utm_source/medium/campaign/content
```

- **Destination (Q2 2026):** `https://fieldsestate.com.au/market-intelligence/Robina`
- **Print vs PDF:** the same code serves both. Append `?m=pdf` to the encoded URL
  for a PDF-only build and the medium lands in `asset_scans.medium` +
  `utm_content`; the printed copy defaults to `print`.
- **Unknown codes never 404** — they log and redirect to the homepage, so a code
  that outlives its registry entry still works on paper.
- **Regenerating is idempotent** — re-running the script does not reset
  `scan_count`, so it is safe to re-run mid-issue.

Each new issue needs its own code (`--quarter Q3 --issue 03`) and a matching
`src` in the cover's `.cover-qr` block. Verify before any print run:

```bash
python3 pipeline/generate_issue_qr.py --quarter Q3 --year 2026 --issue 03 \
    --verify-pdf ../issues/q3_2026_quarterly/latest.pdf
```

`--verify-pdf` decodes the cover straight out of the rendered PDF at 150/300/600
dpi. This is the check that catches the cover still pointing at last quarter's
code — the symbol can be flawless and the issue attribution still wrong.

## Producing a new issue (workflow)
1. Refresh data: `fci_calculator.py`, `generate_charts.py`, `manual_market_pulse.py --show-data`.
2. `render_quarterly.py --regen-charts` to pull fresh charts into the slots.
3. Author the quarter-specific pages in `index.html` (cover number/date, editor's letter, the three suburb sections + case studies, reflection). We have Q2 2026 content ready from the earlier Market-Pulse work (FCI 94.4; the CGT policy section; six case studies read through the *Before You List* method; About Will) to drop in.
4. Add the 3 suburb charts (once source exists).
5. `generate_issue_qr.py --quarter Qn --year YYYY --issue NN`, then point the cover's `.cover-qr` `<img src>` at the new file.
6. `render_quarterly.py --out q2_2026_quarterly` and QA every page.
7. Re-run `generate_issue_qr.py ... --verify-pdf issues/<label>/latest.pdf` and confirm all three dpi rows PASS.

## Open items
1. **3 custom suburb charts** — get the developer's source or replicate in `generate_charts.py`.
2. **page-14 chart slot** — developer shipped the distributions chart on the indexed-price page; corrected in CHART_MAP, applies on next `--sync-charts`.
3. **Q2 editorial authoring** — the content pass to turn this Q1 template into the live Q2 issue.
4. **Cover** — clean number-only cover (no F-mask photo device); confirm with the designer/developer whether the F-pillar cover is wanted.
5. Once content is parametrised, wire `{{ variables }}` for the pure data seams (dates, cover number, per-suburb stats) so those stop being hand-edited.
