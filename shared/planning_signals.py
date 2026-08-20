"""shared/planning_signals.py — derived Gold Coast City Plan development signals.

Conjunction Program Tier 3.1. Will did a full day of manual Development.i + City Plan
V13 analysis for 93 Burleigh Street to answer one question: "is there a real
development angle, or just an 822 m² LDR block?" This module encodes the *reasoning*
so it never has to be redone by hand — you feed it the parsed planning layers from a
Council property report and it computes the derived signals and the honest verdict.

It deliberately does NOT scrape Council (the parcel City Plan UI 403s automated
access). The parse-the-PDF step is `scripts/ingest_cityplan_report.py`; this module is
the pure logic that runs on the extracted layers, so it is unit-testable without a PDF.

The rules encoded here are the current V13 Low Density Residential facts Will
established for 93 Burleigh:
  * LDR default minimum lot size = 600 m²; sub-600 (down to 400) needs dual frontage,
    a Minimum Lot Size overlay, or an existing dual-occupancy/multiple-dwelling.
  * With NO Residential Density overlay, the density benchmark is 1 dwelling / 400 m².
  * Dual occupancy / multiple dwelling in LDR is *intended* only where the lot has dual
    frontage or is mapped RD1+; missing that gate, it falls to IMPACT assessment.
  * LDR front setback benchmark = 6 m (the likely origin of a vendor's "6m relaxation").

⚠ These are planning-code heuristics to TARGET investigation, not legal advice and not
a development approval. Every output carries that caveat. Rule 5: no advice; the verdict
is framed as "worth a town-planner's look" / "no easy pathway", never "you can build X".
"""

from typing import Optional, Dict

LDR_MIN_LOT_SQM = 600.0
LDR_SUBMIN_FLOOR_SQM = 400.0          # smallest lot achievable via the sub-600 pathways
LDR_UNMAPPED_DENSITY_SQM_PER_DW = 400.0   # 1 dwelling / 400 m² when no RD overlay
LDR_FRONT_SETBACK_M = 6.0
DUAL_OCC_FRONTAGE_BENCHMARK_M = 20.0   # Dual Occupancy Code road-frontage benchmark


def assess_planning(layers: Dict) -> Dict:
    """Given parsed City Plan layers, return derived development signals + verdict.

    `layers` expected keys (all optional; None = unknown, which is reported honestly):
      zone: str                         e.g. "Low density residential"
      land_area_sqm: float
      residential_density_overlay: bool|None   True if an RD overlay (RD1+) is mapped
      residential_density_code: str|None        e.g. "RD1" if known
      minimum_lot_size_overlay: bool|None
      dwelling_house_overlay: bool|None
      flood_assessment_required: bool|None
      acid_sulfate_soils: bool|None
      dual_frontage: bool|None
      frontage_m: float|None
      existing_dual_occupancy: bool|None
      da_applications_nil: bool|None            True if Development.i shows "Nil"
    """
    out = {"inputs": dict(layers), "signals": {}, "flags": [], "verdict": None,
           "caveat": ("Planning-code heuristics to guide investigation only — not legal "
                      "advice, not a development approval. Confirm with a town planner and "
                      "Council. Rule 5: never state a buyer 'can' build anything.")}
    s = out["signals"]
    zone = (layers.get("zone") or "").strip().lower()
    is_ldr = "low density residential" in zone
    s["is_low_density_residential"] = is_ldr
    area = layers.get("land_area_sqm")

    # --- Density: dwellings the default benchmark would permit (no RD overlay) ---
    rd_overlay = layers.get("residential_density_overlay")
    if area and (rd_overlay is False or rd_overlay is None):
        max_dw = area / LDR_UNMAPPED_DENSITY_SQM_PER_DW
        s["unmapped_density_dwellings"] = round(max_dw, 2)
        s["sqm_per_dwelling_if_two"] = round(area / 2.0, 1) if area else None
        s["two_dwellings_meet_density_benchmark"] = bool(area / 2.0 >= LDR_UNMAPPED_DENSITY_SQM_PER_DW)
        s["density_buffer_sqm_for_two"] = round(area - 2 * LDR_UNMAPPED_DENSITY_SQM_PER_DW, 1)
    else:
        s["unmapped_density_dwellings"] = None
        s["two_dwellings_meet_density_benchmark"] = None

    # --- The dual-occupancy locational gate ---
    dual_frontage = layers.get("dual_frontage")
    rd1_plus = bool(rd_overlay)  # any RD mapping counts as "RD1 or greater" for the gate
    if dual_frontage is None and rd_overlay is None:
        s["dual_occ_easy_pathway"] = None
        s["dual_occ_pathway_note"] = "unknown — need dual-frontage + RD-overlay facts"
    else:
        easy = bool(dual_frontage) or rd1_plus
        s["dual_occ_easy_pathway"] = easy
        s["dual_occ_assessment_likely"] = "code/accepted" if easy else "impact"
        s["dual_occ_pathway_note"] = (
            "has the accepted pathway (dual frontage or RD1+ mapped)" if easy
            else "no dual frontage and no RD1+ overlay — a dual occupancy would likely be "
                 "IMPACT assessable (full DA + public notification), not an entitlement")

    # --- Frontage vs the dual-occ benchmark ---
    frontage = layers.get("frontage_m")
    if frontage is not None:
        s["frontage_m"] = frontage
        s["meets_dualocc_frontage_benchmark"] = bool(frontage >= DUAL_OCC_FRONTAGE_BENCHMARK_M)

    # --- Simple 1-into-2 freehold subdivision test ---
    if area is not None:
        mls_overlay = layers.get("minimum_lot_size_overlay")
        has_submin_pathway = bool(dual_frontage) or bool(mls_overlay) or bool(layers.get("existing_dual_occupancy"))
        # two ordinary lots need 2 x 600; sub-600 (to 400) needs a pathway
        s["two_compliant_600_lots_possible"] = bool(area >= 2 * LDR_MIN_LOT_SQM)
        s["two_submin_lots_pathway_exists"] = has_submin_pathway
        s["simple_1into2_subdivision"] = bool(
            area >= 2 * LDR_MIN_LOT_SQM or (area >= 2 * LDR_SUBMIN_FLOOR_SQM and has_submin_pathway)
        )

    # --- Setback note (the "6m relaxation" hypothesis) ---
    s["ldr_front_setback_benchmark_m"] = LDR_FRONT_SETBACK_M
    s["setback_relaxation_hypothesis"] = (
        "The LDR front setback benchmark is 6 m — a vendor's '6m relaxation' most likely "
        "refers to a front-setback/building-line variation, not density or subdivision. "
        "Confirm with the actual Council approval/survey; Development.i showing Nil means no "
        "documentary trace was located there."
    ) if layers.get("da_applications_nil") else (
        "The LDR front setback benchmark is 6 m — a '6m relaxation' most likely refers to a "
        "front-setback variation. Check Development.i and Council building records for the approval."
    )

    # --- Constraints worth flagging for a developer buyer ---
    if layers.get("flood_assessment_required"):
        out["flags"].append("Flood assessment required for a development application.")
    if layers.get("acid_sulfate_soils"):
        out["flags"].append("Acid sulfate soils mapped — earthworks/fill/drainage become planning/engineering considerations.")
    if layers.get("dwelling_house_overlay"):
        out["flags"].append("Dwelling House Overlay — Council intent favours detached-house character; reinforces that this is not a hidden medium-density parcel.")
    if layers.get("da_applications_nil"):
        out["flags"].append("Development.i shows Nil applications — no hidden approved DA/duplex/subdivision on this parcel.")

    # --- Honest verdict ---
    two_ok = s.get("two_dwellings_meet_density_benchmark")
    easy = s.get("dual_occ_easy_pathway")
    if not is_ldr:
        out["verdict"] = ("Not Low Density Residential on the supplied layers — reassess the whole "
                          "development angle against the actual zone.")
    elif two_ok and easy is False:
        out["verdict"] = (
            "NUANCED: two dwellings would satisfy the zone's default density benchmark "
            f"({s.get('sqm_per_dwelling_if_two')} m²/dwelling vs {int(LDR_UNMAPPED_DENSITY_SQM_PER_DW)} m² benchmark), "
            "BUT with no dual frontage and no RD1+ overlay a dual occupancy would likely be impact "
            "assessable — a real planning argument to investigate with a town planner, not an "
            "automatic entitlement. Do not market as 'duplex site' or 'development block'.")
    elif two_ok and easy:
        out["verdict"] = ("Two dwellings meet the density benchmark AND the site has the accepted "
                          "locational pathway (dual frontage or RD1+). Worth a town-planner's confirmation.")
    elif two_ok is False:
        out["verdict"] = ("Two dwellings would exceed the zone's default density benchmark on this area — "
                          "a density departure would have to be argued. Weak development angle.")
    else:
        out["verdict"] = "Insufficient planning layers supplied to form a development verdict."

    return out
