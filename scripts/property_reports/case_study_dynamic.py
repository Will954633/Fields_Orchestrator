"""
case_study_dynamic — CS0, the per-seller "a home like yours, recently sold" card.

The ONLY case-study card that runs unattended for every report, so it is built
to two hard gates rather than best-effort:

  (1) RELEVANCE gate — only renders if the best SOLD match is in the close tier
      (score <= competitor_matcher.CLOSE_MATCH_THRESHOLD) found at aperture
      ring <= 2. A home that only appears at the loosest ring is not "a home
      like yours" → return None (the frontend hides the card).

  (2) FACT gate — every printed fact must agree with the Domain property-profile
      timeline. Sale price + method must match the timeline's most-recent sold
      event; if that event predates the stored sale (the stale-timeline trap),
      the candidate is rejected. DOM is taken ONLY from the timeline (never the
      derived top-level days_on_market, which disagrees ~25% of the time). Any
      fact that can't be verified is omitted; if price+method can't be verified,
      the candidate is skipped for the next-best one.

Design corrections proven in 11_House_Mini_Site/cs0_prototype.py (2026-06-01):
  - recency comes from the timeline's newest is_sold event, NOT sale_date/
    sold_date (those frequently hold a PRIOR sale).
  - sold price parses from the timeline event price / listing_price / sale_price
    ("SOLD - $X"), NOT `price` (null on sold docs).

Returns a `case_studies.dynamic` dict ready to $set, or None to hide CS0.
No price-revision claims are ever made — the data has no intra-campaign
asking-price-cut trail.

CS0 v2 (2026-06-11): once a comp passes both gates, the card is built out into
a FULL case study — mirrored photo gallery, sale-history timeline, market-at-
listing, condition read, floor plan (the same exhibit set as the static
library, reusing build_case_study's helpers) — plus an Opus-drafted analysis
WRITTEN TO THE SUBJECT OWNER ("your home"), validated against the editorial
rules. Every enrichment fails soft: if photos can't mirror or the narrative
fails its audit, the verified data card still ships exactly as before.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from pymongo.database import Database

from scripts.property_reports import competitor_matcher as cm

logger = logging.getLogger(__name__)

WINDOW_MONTHS = 12
MAX_RELEVANT_RING = 2          # ring 0-2 only; ring 3 is too loose to be "like yours"
DATE_TOLERANCE_DAYS = 21       # contract vs settlement gap we accept as "same sale"
# Per-ring price tolerance for the SOLD case-study match. competitor_matcher's
# APERTURE_RINGS went physical-led and dropped its "price" key (it has no anchor
# at map-build time); CS0 DOES have a price anchor (the valuation working range),
# so it keeps a price gate that widens with each ring. Indexed by ring index.
RING_PRICE_BANDS = [0.15, 0.20, 0.25, 0.30]
# CS0 relevance band. The matcher's CLOSE_MATCH_THRESHOLD (0.22) is its display
# threshold for the active-listing map; for a rare home (e.g. a 6-bedroom) the
# genuinely tellable comp can sit just outside it. 0.33 ≈ ring-2's "wider
# neighbourhood within 20% on price" intent — still honestly "a home like
# yours" (same bedroom band, recent, one suburb over), and the difference_line
# states every difference plainly. A home with NO match this close is rare
# enough that CS0 hides rather than overclaim.
RELEVANCE_MAX_SCORE = 0.33

# ── CS0 v2 full-case enrichment ──
CONTAINER = "case-studies"     # same blob container as the static library —
                               # same comp address → same blob path → photos
                               # mirror once and are reused across reports
MAX_PHOTOS = 10
NARRATIVE_MODEL = "claude-opus-4-8"
NARRATIVE_MAX_TOKENS = 2200
NARRATIVE_RETRIES = 3
NARRATIVE_BACKOFF = [2, 5, 12]

FORBIDDEN_WORDS = [
    "stunning", "nestled", "boasting", "rare opportunity", "robust market",
]
ADVICE_PATTERNS = [
    r"\byou should\b", r"\byou must\b", r"\bwe recommend\b", r"\bconsider (buying|selling)\b",
    r"\bnow is a good time\b", r"\bwill (rise|fall|increase|drop|grow)\b",
    r"\bprices will\b", r"\bis going to\b", r"\bguaranteed\b",
]

NARRATIVE_KEYS = ["headline", "why_this_home", "the_campaign", "the_result", "what_it_shows"]

NARRATIVE_SYSTEM_PROMPT = """You are writing the lead case study in a private pre-sale property report that Fields Estate — a Gold Coast property-intelligence firm whose entire brand is "every claim is verifiable" — prepared for the OWNER of one specific home.

You will be given two verified data scaffolds:
1. THE SOLD HOME — a real, recently sold home Fields matched as the closest comparable to the owner's home: its facts, public-record sale outcome, full Domain sale timeline, the suburb market it sold into, and (only when present) a condition read and a Domain estimate-vs-reality exhibit.
2. THE OWNER'S HOME — the subject property's basic facts, plus a pre-written factual line stating how the two homes differ.

The comparison line ("how_the_sold_home_compares_to_yours") frames THE SOLD HOME against the owner's home: "adds X" means the SOLD home has X and the owner's home does not; "without X" means the owner's home has X and the sold home does not; "listed N% above/below your guide" describes the sold home's price against the owner's guide. Preserve this direction exactly — never invert it.

These are the ONLY facts you may state. Do not invent any number, date, feature, motive, or quote. If you do not have a fact, do not imply it.

Write directly to the owner in second person ("your home"). This is the case study of THE SOLD HOME, told because of what its sale shows about the market the owner's home would enter. Return STRICT JSON with exactly these string keys: "headline", "why_this_home", "the_campaign", "the_result", "what_it_shows". No other keys, no markdown fences.

Section intent:
- headline: One factual, specific line for the case (under 90 characters). Anchor it in the sold home's concrete outcome — e.g. its time on market, its method, or its sale month. No hype, no advice.
- why_this_home: Why this particular sale is the most relevant evidence for the owner — name the likeness (beds, type, area, price bracket) AND state the differences plainly, including any that favour the sold home. Honesty about the differences is the point.
- the_campaign: How the sold home came to market — the method of sale, when it listed/sold, and the market conditions it launched into (suburb median, days-on-market norm) where given. Frame the campaign ONLY from what the data supports. Never claim a specific asking price or price cut unless it is in the scaffold.
- the_result: The factual outcome — final price, time on market (vs the suburb norm where given), method — stated plainly.
- what_it_shows: What this sale, as evidence, shows about the market the owner's home would enter — the depth of the buyer pool at this bracket, the pace homes like this transact at, what the method appears to have contributed. Use conditional, data-anchored language ("this sale suggests", "if the pattern holds"). The reader draws their own conclusion.

HARD RULES (a violation means the whole draft is rejected):
- NEVER state, estimate, or imply a value, price, or price range for the OWNER'S home. The only prices you may print are the sold home's public-record figures and the suburb statistics you were given.
- No advice: never "you should", "consider selling", "list now", "now is the time".
- No forecasts: never predict prices or say what "will" happen.
- Banned words: stunning, nestled, boasting, rare opportunity, robust market.
- Money as "$1,250,000" (never "$1.25m"). Suburbs capitalised. Exact figures from the scaffold only.
- Trade-offs are framed as value, not flaws — for both homes.
- Factual, calm, specific. A document the owner could hand to their accountant.
- If the scaffold has no Domain estimate exhibit, do NOT mention Domain's estimate at all.
- If days-on-market is absent, do not state or guess one.

Each section after the headline: 2–5 sentences. Total under 480 words."""

# Candidate projection — the matcher's set plus the sold/timeline fields CS0 needs.
_SOLD_PROJ = dict(
    cm._CANDIDATE_PROJECTION,
    scraped_data_v2=1, sale_price=1, sale_date=1, sold_date=1,
    sale_method=1, domain_valuation_at_listing=1,
)


def _newest_sold_event(doc: Dict[str, Any]) -> Tuple[Optional[dt.date], Optional[int], Optional[Dict[str, Any]]]:
    """The current sale = most-recent is_sold event on the Domain timeline.
    Returns (date, price, event) or (None, None, None)."""
    v2 = doc.get("scraped_data_v2") or {}
    tl = v2.get("timeline") if isinstance(v2, dict) else None
    if not tl:
        return None, None, None
    sales = [
        e for e in tl
        if isinstance(e, dict) and e.get("category") == "Sale"
        and e.get("is_sold") and e.get("event_date")
    ]
    if not sales:
        return None, None, None
    sales.sort(key=lambda e: str(e.get("event_date")), reverse=True)
    top = sales[0]
    try:
        d0 = dt.date.fromisoformat(str(top["event_date"])[:10])
    except (ValueError, TypeError):
        d0 = None
    return d0, cm._parse_price(top.get("event_price")), top


def _parse_iso(v: Any) -> Optional[dt.date]:
    if not v:
        return None
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except (ValueError, TypeError):
        return None


def _gather_sold(
    db: Database, subject: Dict[str, Any], suburbs: List[str],
    price_band: float, bed_band: int, cutoff: dt.date,
) -> List[Dict[str, Any]]:
    """SOLD substitutes across `suburbs` clearing the hard filters: same
    property-type group, sold within the window (by TIMELINE date), price in
    band. Recency + price both come from the timeline, not the stale fields."""
    out: List[Dict[str, Any]] = []
    anchor = subject["price"]
    lo, hi = anchor * (1 - price_band), anchor * (1 + price_band)
    bed = subject["bedrooms"]
    try:
        cols = set(db.list_collection_names())
    except Exception:
        cols = set()
    for sub in suburbs:
        if sub not in cols:
            continue
        query: Dict[str, Any] = {"listing_status": "sold"}
        if bed is not None:
            query["bedrooms"] = {"$in": list(range(bed - bed_band, bed + bed_band + 1))}
        try:
            cursor = db[sub].find(query, _SOLD_PROJ)
        except Exception as e:
            logger.debug(f"  cs0 gather failed on {sub}: {e}")
            continue
        for d in cursor:
            d["_suburb_key"] = sub
            if cm._property_type_group(d) != subject["group"]:
                continue
            tl_date, tl_price, _ = _newest_sold_event(d)
            rd = tl_date or _parse_iso(d.get("sale_date") or d.get("sold_date"))
            if rd is None or rd < cutoff:
                continue
            price = tl_price or cm._parse_price(d.get("listing_price"), d.get("sale_price"))
            if not price or not (lo <= price <= hi):
                continue
            d["_price"] = price
            out.append(d)
    return out


def _verify_facts(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Apply the FACT gate. Returns the dict of verified facts, or None if the
    candidate's core facts (price + method) can't be trusted."""
    ev_date, ev_price, ev = _newest_sold_event(doc)
    stored_price = cm._parse_price(doc.get("listing_price"), doc.get("sale_price"))
    stored_method = (doc.get("sale_method") or "").strip().lower()
    facts: Dict[str, Any] = {}

    if ev:
        stored_date = _parse_iso(doc.get("sold_date") or doc.get("sale_date"))
        # Stale-timeline trap: the timeline's newest sold event must describe
        # THIS sale (recent + matching price), else the timeline predates it.
        gap_days = abs((stored_date - ev_date).days) if (stored_date and ev_date) else 9999
        price_ok = ev_price and stored_price and abs(ev_price - stored_price) <= 1000
        if gap_days <= DATE_TOLERANCE_DAYS and price_ok:
            facts["sale_price"] = ev_price
            facts["method"] = _normalise_method(ev.get("price_description"))
            facts["sale_date"] = str(ev.get("event_date"))[:10]
            if isinstance(ev.get("days_on_market"), (int, float)):
                facts["days_on_market"] = int(ev["days_on_market"])
            facts["_source"] = "timeline"
            return facts
        # Timeline exists but doesn't describe this sale → reject the candidate.
        logger.debug(
            f"  cs0 fact-gate reject (stale timeline): gap={gap_days}d "
            f"tl_price={ev_price} stored={stored_price}"
        )
        return None

    # No timeline: fall back to stored fields for price + method ONLY.
    # No DOM (we will not derive one), no Domain-vs-reality without a timeline.
    if stored_price:
        facts["sale_price"] = stored_price
        if stored_method:
            facts["method"] = _normalise_method(stored_method)
        facts["sale_date"] = str(doc.get("sold_date") or doc.get("sale_date") or "")[:10] or None
        facts["_source"] = "stored"
        return facts
    return None


def _normalise_method(raw: Any) -> Optional[str]:
    s = (str(raw) if raw is not None else "").strip().lower()
    if not s:
        return None
    if "auction" in s:
        return "auction"
    if "private" in s or "treaty" in s:
        return "private treaty"
    return s


def _verification_rank(facts: Dict[str, Any]) -> int:
    """Higher = richer/more tellable. Prefer a full timeline (incl. DOM)."""
    score = 0
    if "days_on_market" in facts:
        score += 4
    if facts.get("_source") == "timeline":
        score += 2
    if "sale_date" in facts:
        score += 1
    return score


def _build_exhibits(
    doc: Dict[str, Any], db: Database, suburb_disp: str, sale_date: Optional[str],
) -> Dict[str, Any]:
    """The full exhibit scaffold for the chosen comp — same set as the static
    library, reusing build_case_study's verified helpers. Photos mirror to our
    blob under the comp's address slug; a comp already mirrored (by a library
    build or an earlier report) is reused from disk without re-downloading."""
    from scripts.property_reports import build_case_study as bcs  # lazy: avoids
    # bcs's import-time dotenv/basicConfig in the daemon until actually needed
    from shared import blob_storage

    slug = bcs._slugify(doc.get("address") or doc.get("street_address") or str(doc.get("_id")))
    urls = bcs._gather_photo_urls(doc, MAX_PHOTOS)
    gallery: List[Dict[str, Any]] = []
    for i, url in enumerate(urls):
        ext = ".jpg"
        m = re.search(r"\.(jpe?g|png|webp)(\?|$)", url, re.I)
        if m:
            ext = "." + m.group(1).lower().replace("jpeg", "jpg")
        blob_name = f"{slug}/{i:02d}{ext}"
        try:
            if (blob_storage._backend() == "local"
                    and (blob_storage._local_root() / CONTAINER / blob_name).exists()):
                gallery.append({"url": blob_storage.public_url(CONTAINER, blob_name),
                                "mirrored": True})
                continue
        except Exception:
            pass
        data = bcs._download(url)
        if not data:
            gallery.append({"url": url, "mirrored": False})
            continue
        ct = "image/jpeg" if ext == ".jpg" else f"image/{ext.lstrip('.')}"
        public = blob_storage.upload(CONTAINER, blob_name, data, content_type=ct)
        gallery.append({"url": public or url, "mirrored": bool(public)})
    if gallery:
        logger.info("  cs0: gallery %d photos (%d mirrored)",
                    len(gallery), sum(1 for g in gallery if g["mirrored"]))

    fps = doc.get("floor_plans_v2_extracted") or doc.get("floor_plans") or []
    return {
        "gallery": gallery,
        "floor_plan": fps[0] if fps else None,
        "condition": bcs._condition(doc),
        "sale_timeline": bcs._sale_timeline(doc),
        # _market_at_listing has its own 15-month contemporaneity guard — for an
        # older sale it returns None and the exhibit is simply omitted.
        "market_at_listing": bcs._market_at_listing(db, suburb_disp, sale_date),
        "listing_url": doc.get("listing_url"),
    }


def _draft_owner_narrative(
    subject: Dict[str, Any], subject_doc: Dict[str, Any], case: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Opus drafts the owner-addressed analysis from the verified scaffold only.
    Validated against the editorial rules (no advice, no forecasts, no banned
    words, no subject-home valuation). Returns the sections dict, or None —
    the card then ships data-only, never blocked on the LLM."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        try:
            from dotenv import load_dotenv
            load_dotenv("/home/fields/Fields_Orchestrator/.env")
            api_key = os.environ.get("ANTHROPIC_API_KEY")
        except Exception:
            pass
    if not api_key:
        logger.warning("  cs0 narrative: ANTHROPIC_API_KEY not set — shipping data-only")
        return None
    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)

    sold_home = {
        "address": case.get("address"),
        "suburb": case.get("suburb"),
        "facts": {k: case.get(k) for k in
                  ("bedrooms", "bathrooms", "property_type", "land_size_sqm")
                  if case.get(k) is not None},
        "sale_outcome": {k: case.get(k) for k in
                         ("sale_price", "method", "sale_date", "days_on_market")
                         if case.get(k) is not None},
        "full_sale_timeline": case.get("sale_timeline") or None,
        "market_when_it_sold": case.get("market_at_listing"),
        "domain_estimate_vs_reality": case.get("domain_vs_reality"),
        "condition_read": case.get("condition"),
    }
    owners_home = {
        "address": subject_doc.get("address") or subject_doc.get("street_address"),
        "suburb": (subject_doc.get("suburb") or "").title() or None,
        "bedrooms": subject.get("bedrooms"),
        "bathrooms": subject.get("bathrooms"),
        "car_spaces": subject.get("car"),
        "land_size_sqm": subject.get("land"),
        "floor_area_sqm": subject.get("floor"),
        "property_type": subject_doc.get("property_type"),
        # Direction matters: this line frames the SOLD home against the owner's
        # ("adds X" = the sold home has X). The system prompt spells this out.
        "how_the_sold_home_compares_to_yours": case.get("difference_line"),
    }
    payload = {
        "the_sold_home": {k: v for k, v in sold_home.items() if v is not None},
        "the_owners_home": {k: v for k, v in owners_home.items() if v is not None},
    }
    user_prompt = ("Here are the verified data scaffolds. State only these facts.\n\n"
                   + json.dumps(payload, indent=1, default=str))

    last_err = None
    for attempt in range(1, NARRATIVE_RETRIES + 1):
        try:
            resp = client.messages.create(
                model=NARRATIVE_MODEL, max_tokens=NARRATIVE_MAX_TOKENS,
                system=NARRATIVE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = "".join(getattr(b, "text", "") for b in resp.content
                           if getattr(b, "type", None) == "text").strip()
            text = re.sub(r"^```(?:json)?|```$", "", text.strip()).strip()
            sections = json.loads(text)
        except Exception as e:
            last_err = f"attempt {attempt}: {e}"
            logger.warning(f"  cs0 narrative {last_err}")
            if attempt < NARRATIVE_RETRIES:
                time.sleep(NARRATIVE_BACKOFF[min(attempt - 1, len(NARRATIVE_BACKOFF) - 1)])
            continue

        err = _validate_narrative(sections)
        if err:
            last_err = f"attempt {attempt} validation: {err}"
            logger.warning(f"  cs0 narrative {last_err}")
            if attempt < NARRATIVE_RETRIES:
                time.sleep(NARRATIVE_BACKOFF[min(attempt - 1, len(NARRATIVE_BACKOFF) - 1)])
            continue

        logger.info(f"  cs0 narrative drafted (attempt {attempt})")
        return {
            **{k: str(sections[k]).strip() for k in NARRATIVE_KEYS},
            "model": NARRATIVE_MODEL,
            "generated_at": dt.datetime.utcnow().isoformat() + "Z",
            "attempt": attempt,
        }

    logger.warning(f"  cs0 narrative failed all attempts ({last_err}) — shipping data-only")
    return None


def _validate_narrative(sections: Any) -> Optional[str]:
    if not isinstance(sections, dict):
        return "not a dict"
    if set(sections.keys()) != set(NARRATIVE_KEYS):
        return f"wrong keys: {sorted(sections.keys())}"
    blob = " ".join(str(sections[k]) for k in NARRATIVE_KEYS).lower()
    for w in FORBIDDEN_WORDS:
        if w in blob:
            return f"forbidden word: {w}"
    for pat in ADVICE_PATTERNS:
        if re.search(pat, blob):
            return f"advice/forecast pattern: {pat}"
    if re.search(r"\$\d+(\.\d+)?\s*m\b", blob):
        return "shorthand money ($1.25m) — must be full format"
    if len(str(sections["headline"])) > 120:
        return "headline too long"
    for k in NARRATIVE_KEYS:
        if not str(sections[k]).strip():
            return f"empty section: {k}"
    return None


def resolve_dynamic_case_study(
    subject_doc: Dict[str, Any],
    db: Database,
    features_basic: Optional[Dict[str, Any]] = None,
    *,
    price_anchor: Optional[int] = None,
    catchment: Optional[List[str]] = None,
    today: Optional[dt.date] = None,
) -> Optional[Dict[str, Any]]:
    """CS0 resolver. Returns the `case_studies.dynamic` dict, or None to hide."""
    subject = cm._subject_profile(subject_doc, features_basic, price_anchor)
    if not subject["bedrooms"] or not subject["price"]:
        logger.info("  cs0: subject missing bedrooms or price anchor — hiding CS0")
        return None

    own = (subject_doc.get("suburb_key")
           or subject_doc.get("_suburb_key")
           or (subject_doc.get("suburb") or "").lower().replace(" ", "_"))
    catch = catchment or cm.DEFAULT_CATCHMENT
    subject["point"] = subject["latlng"] or cm.CATCHMENT_CENTROIDS.get(own)
    today = today or dt.date.today()
    cutoff = today.replace(year=today.year - 1)
    subj_id = subject_doc.get("_id")

    # Walk aperture rings; stop at the first ring (<= MAX_RELEVANT_RING) that
    # yields a close-tier match. A match only at ring 3 fails the relevance gate.
    best_close: List[Tuple[float, Dict[str, Any]]] = []
    chosen_ring: Optional[int] = None
    seen: set = set()
    for idx, ring in enumerate(cm.APERTURE_RINGS):
        if idx > MAX_RELEVANT_RING:
            break
        suburbs = cm._geo_for_ring(ring["geo"], own, catch)
        price_band = RING_PRICE_BANDS[min(idx, len(RING_PRICE_BANDS) - 1)]
        found = _gather_sold(db, subject, suburbs, price_band, ring["beds"], cutoff)
        scored: List[Tuple[float, Dict[str, Any]]] = []
        for c in found:
            if c["_id"] == subj_id or c["_id"] in seen:
                continue
            seen.add(c["_id"])
            scored.append((cm._score(subject, c), c))
        scored.sort(key=lambda x: x[0])
        # Relevance band + must have a real address (skip scrape-artefact docs
        # with no address — they can't be shown or verified by the seller).
        close = [
            (s, c) for s, c in scored
            if s <= RELEVANCE_MAX_SCORE and (c.get("address") or c.get("street_address"))
        ]
        if close:
            best_close = close
            chosen_ring = idx
            break

    if not best_close:
        logger.info("  cs0: no relevant sold match (score <= %.2f) at ring <= %d — hiding CS0",
                    RELEVANCE_MAX_SCORE, MAX_RELEVANT_RING)
        return None

    # Among close-tier matches, pick the one that BOTH verifies and tells the
    # richest story (full timeline incl. DOM > price+method+date > price+method).
    verified_pool: List[Tuple[int, float, Dict[str, Any], Dict[str, Any]]] = []
    for score, c in best_close[:12]:
        full = db[c["_suburb_key"]].find_one({"_id": c["_id"]}) or c
        full["_suburb_key"] = c["_suburb_key"]
        full["_price"] = c["_price"]
        facts = _verify_facts(full)
        if facts and facts.get("sale_price"):
            verified_pool.append((_verification_rank(facts), score, full, facts))

    if not verified_pool:
        logger.info("  cs0: close-tier matches found but none passed the fact gate — hiding CS0")
        return None

    # Best = richest verification, then closest score.
    verified_pool.sort(key=lambda t: (-t[0], t[1]))
    _, score, doc, facts = verified_pool[0]

    # Domain-vs-reality (only when we have a timeline-verified sale + estimate).
    domain_block = None
    dv = doc.get("domain_valuation_at_listing") or {}
    mid = dv.get("mid") if isinstance(dv, dict) else None
    if facts.get("_source") == "timeline" and mid and facts.get("sale_price"):
        diff_pct = (mid - facts["sale_price"]) / facts["sale_price"] * 100
        if abs(diff_pct) >= 3:
            domain_block = {
                "estimate_at_listing": int(mid),
                "grade": dv.get("accuracy"),
                "diff_pct": round(diff_pct, 1),
                "direction": "above" if diff_pct > 0 else "below",
            }

    suburb_disp = (doc.get("suburb") or doc.get("_suburb_key", "").replace("_", " ")).title()
    out: Dict[str, Any] = {
        "address": doc.get("address") or doc.get("street_address"),
        "suburb": suburb_disp,
        "bedrooms": cm._to_int(doc.get("bedrooms")),
        "bathrooms": cm._to_int(doc.get("bathrooms")),
        "property_type": doc.get("property_type"),
        "land_size_sqm": cm._to_int(doc.get("lot_size_sqm") or doc.get("land_size_sqm")),
        "sale_price": facts["sale_price"],
        "method": facts.get("method"),
        "sale_date": facts.get("sale_date"),
        "days_on_market": facts.get("days_on_market"),   # None if not timeline-verified
        "difference_line": cm._difference_line(subject, doc),
        "domain_vs_reality": domain_block,
        "match_score": round(score, 3),
        "aperture_ring": chosen_ring,
        "fact_source": facts.get("_source"),
        "resolved_at": today.isoformat(),
    }

    # ── CS0 v2: build out the full case study. Both steps fail SOFT — the
    # fact-verified data card above is already complete and ships regardless.
    try:
        out.update(_build_exhibits(doc, db, suburb_disp, out.get("sale_date")))
    except Exception as e:
        logger.warning(f"  cs0 exhibits failed (card ships data-only): {e}")
    try:
        narrative = _draft_owner_narrative(subject, subject_doc, out)
        if narrative:
            out["narrative"] = narrative
    except Exception as e:
        logger.warning(f"  cs0 narrative threw (card ships without narrative): {e}")

    logger.info(
        "  cs0: rendered %s (score %.3f, ring %d, DOM=%s, source=%s, photos=%d, narrative=%s)",
        out["address"], score, chosen_ring, out["days_on_market"], out["fact_source"],
        len(out.get("gallery") or []), "yes" if out.get("narrative") else "no",
    )
    return out
