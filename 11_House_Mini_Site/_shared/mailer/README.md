# Homeowner Mailer — bespoke, data-driven, one PDF per address

Direct-mail leaflet that drives homeowners to scan a QR and open their own Fields
home report. **Every mailer is generated from that property's own report data** —
its real competitor count, comparable sales, buyer profile, school distance, hero
photo and aerial parcel — plus a QR to that home's `/your-home/<slug>`. Postal
address, data, imagery and QR all come from the same `property_reports` record, so
nothing can drift.

Strategy (per the 2026-07-17 copy review): lead with the surprising, address-specific
revelation — **"Only N of TOTAL homes for sale genuinely compete with yours"** — then
make scanning the only way to see which ones. Readable real stats + the home's real
photo replace the old tiny full-page screenshot.

## Files
- `mailer_template.html` — the template. Placeholders filled per address:
  `{{STREET}} {{LOCALITY}} {{SUBURB}} {{TRUE_COMP}} {{TOTAL_ACTIVE}} {{FULL_STACK}}
  {{COMPS_REVIEWED}} {{SCHOOL}} {{SCHOOL_M}} {{PERSONA}} {{HERO_IMG}} {{AERIAL_IMG}} {{QR_IMG}}`.
- `generate_mailers.py` — pulls data + downloads the home's photo/aerial + QR → bespoke PDF.
- `assets/gen/<slug>/` — per-address hero.jpg, aerial.png, qr.png.
- `output/<slug>.pdf` — bespoke mailers. `output/all_mailers.pdf` — combined print file.
- `Fields_Home_Report_Mailer_SAMPLE.pdf` — a viewable example (25 Huntingdale).
- `capture_report_shots.js` / `prep_assets.py` — legacy static-screenshot tooling (superseded).

## Data source (per address, from property_reports)
| Mailer field | Source |
|---|---|
| N genuine competitors | `len(comparables.closest_active)` |
| TOTAL active listings | `scarcity_features.active_listings_total` |
| FULL_STACK matches | `scarcity_features.active_matching_full_stack` |
| Comparable sales reviewed | `valuation.model_range.comp_count` |
| School + walk metres | `pois` (category=school) |
| Buyer persona | `positioning.personas[0].label` |
| Hero photo / aerial | `property.photos[0].url` / `property.satellite.satellite_image_url` |

## Readiness gate
A mailer is only generated when the report is `build_state=complete`, its
`scarcity`/`competitor_matches` slots are approved, and all headline fields are
present. Addresses that aren't ready are refused (they'd otherwise print a QR to a
thin report or a mailer with blank numbers). ~15 of 24 current reports pass.

## Usage
```bash
source /home/fields/venv/bin/activate
set -a && source /home/fields/Fields_Orchestrator/.env && set +a
cd /home/fields/Fields_Orchestrator/11_House_Mini_Site/mailer

python3 generate_mailers.py --slug 25-huntingdale-crescent-robina   # one address
python3 generate_mailers.py --all-complete --combine                 # every ready home → one print file
python3 generate_mailers.py --slug <s> --dry-run                     # print extracted copy, no PDF
```

## Notes
- QR carries `utm_source=mailer&utm_medium=print&utm_campaign=home_report`.
- Editorial (CLAUDE.md §5): no single valuation in the headline (competition-led), ranges
  only, no advice/forecasts, no "scraped", trade-offs framed as value.
- Two-stage honesty: competition/buyer/positioning analysis is live now; the
  consultant-reviewed valuation lands within three business days — stated on the mailer.
