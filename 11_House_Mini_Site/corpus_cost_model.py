#!/usr/bin/env python3
"""
corpus_cost_model.py — what it costs to pre-populate /your-home for the whole target market.

Token counts marked MEASURED were obtained 2026-08-12 by issuing real Vertex
gemini-2.5-flash calls with the production prompts and reading `usageMetadata`.
Counts marked EST are reasoned from the same 1,290-tokens-per-image constant
(Gemini bills 640x640 and 640x640@scale2 identically at 1290) plus the measured
prompt lengths.

Run:  python3 corpus_cost_model.py [--corpus 15000]
"""
import argparse

# --- Gemini 2.5 Flash list price (USD per 1M tokens) -------------------------
# CONFIRM before committing spend.
IN_PER_M, OUT_PER_M = 0.30, 2.50

# --- Google Maps Platform list price (USD per 1,000 requests) ----------------
# CONFIRM before committing spend — these dominate at corpus scale.
STATIC_MAPS_PER_K = 2.00      # satellite tile
STREET_VIEW_PER_K = 7.00      # street view still

IMG = 1290  # MEASURED: tokens per image, both tile sizes

def cost(tin, tout):
    return (tin * IN_PER_M + tout * OUT_PER_M) / 1_000_000

# call -> (label, in_tokens, out_tokens, source)
CALLS = {
    "V5_satellite":   ("Satellite analysis",      3063,  829, "MEASURED"),
    "V7_street_view": ("Street view analysis",    2294,  493, "MEASURED"),
    "V1_hero":        ("Hero photo pick (8 img)", 8*IMG+600, 400, "EST"),
    "V2_classify":    ("Floor-plan YES/NO (per photo)", IMG+60, 8, "MEASURED prompt"),
    "V3_floor_plan":  ("Floor-plan room OCR",     IMG+900, 700, "EST"),
    "V4_debrand":     ("Logo bbox detection",     IMG+500, 250, "EST"),
    "V8_photo_cond":  ("Photo condition (20 img)", 20*IMG+1000, 3000, "EST"),
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=int, default=15000, help="addresses to pre-populate")
    ap.add_argument("--with-photos", type=int, default=16116, help="of those, how many have photos")
    ap.add_argument("--pvd-done", type=int, default=12030, help="already have property_valuation_data")
    ap.add_argument("--with-floorplan", type=int, default=5000)
    ap.add_argument("--avg-photos", type=int, default=20, help="photos per listing (V2 fires once each)")
    a = ap.parse_args()

    N = a.corpus
    photo_n = min(a.with_photos, N)
    pvd_marginal = max(0, photo_n - a.pvd_done)

    print(f"corpus={N}  with_photos={photo_n}  pvd_marginal={pvd_marginal}\n")
    print(f"{'call':<18} {'unit $':>9} {'count':>8} {'total $':>9}  source")
    print("-" * 62)

    rows = []
    def row(key, count, mult=1):
        label, ti, to, src = CALLS[key]
        u = cost(ti, to) * mult
        rows.append((key, label, u, count, u * count, src))
        print(f"{key:<18} {u:>9.5f} {count:>8} {u*count:>9.2f}  {src}")

    row("V5_satellite",   N)
    row("V7_street_view", N)
    row("V1_hero",        photo_n)
    row("V2_classify",    photo_n, mult=a.avg_photos)   # fires once PER PHOTO
    row("V3_floor_plan",  a.with_floorplan)
    row("V4_debrand",     a.with_floorplan)
    row("V8_photo_cond",  pvd_marginal)

    ai_total = sum(r[4] for r in rows)

    # --- image acquisition, billed per request, independent of the model -----
    tile = N * STATIC_MAPS_PER_K / 1000
    sv   = N * STREET_VIEW_PER_K / 1000
    print("-" * 62)
    print(f"{'Static Maps tile':<18} {STATIC_MAPS_PER_K/1000:>9.5f} {N:>8} {tile:>9.2f}  list price")
    print(f"{'Street View still':<18} {STREET_VIEW_PER_K/1000:>9.5f} {N:>8} {sv:>9.2f}  list price")

    print("=" * 62)
    print(f"{'AI (Gemini) total':<40} ${ai_total:>9.2f}")
    print(f"{'Image fetch (Google Maps) total':<40} ${tile+sv:>9.2f}")
    print(f"{'FULL EVERYTHING':<40} ${ai_total+tile+sv:>9.2f}")

    # --- scenarios ----------------------------------------------------------
    by = {r[0]: r[4] for r in rows}
    lean = by["V5_satellite"] + by["V7_street_view"] + by["V3_floor_plan"] + by["V8_photo_cond"]
    minimal = by["V5_satellite"] + by["V7_street_view"]

    print()
    print("SCENARIOS (AI + image fetch)")
    print(f"  A  everything                          ${ai_total+tile+sv:>8.2f}")
    print(f"  B  lean  (drop V1 hero, V2 classify, V4 debrand -> heuristics)")
    print(f"                                         ${lean+tile+sv:>8.2f}")
    print(f"  C  minimal (satellite + street view only)")
    print(f"                                         ${minimal+tile+sv:>8.2f}")
    print(f"  D  on-demand photos/floor plan (C now, rest behind a button)")
    print(f"                                         ${minimal+tile+sv:>8.2f} up-front")
    print()
    print(f"  NOTE: V2_classify alone is ${by['V2_classify']:.2f} — it fires once PER PHOTO")
    print(f"        at max_tokens=8, and `floor_plans_v2_extracted` already answers")
    print(f"        it for 83% of properties. This is the single biggest waste.")

if __name__ == "__main__":
    main()
