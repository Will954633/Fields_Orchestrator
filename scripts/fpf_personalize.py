#!/usr/bin/env python3
"""
fpf_personalize.py — enrichment layer over the Five Property Friday batch.

The stock fpf_send.py reads ONLY the raw form doc (fb_leads.fields /
five_property_friday_subscribers) — so it greets everyone "Hi there", uses the
suburb median as a fake budget, and sends behaviourally-different people the
same suburb list. But we already hold, in system_monitor.crm_contacts:
  - name            (first name for the greeting)
  - lead_brief      (timeframe, owns_gc_home)
  - lead_web        (actual on-site pageviews: which PROPERTIES + which content)

This module resolves that per recipient and produces a *personalised* shortlist:
  1. Surface the homes they actually viewed (still for_sale only) up top, roled
     by our comps gap — "You looked at this; here's our read".
  2. Infer a budget from what they view (falls back to the suburb median).
  3. Weight suburbs by where they've actually shown interest (multi-suburb subs).
  4. Greet by first name; open with a line grounded in their behaviour;
     tone by timeframe.
Editorial rules (CLAUDE.md §5) preserved: comparable RANGES not single figures,
comps language, no advice, no forbidden words, exact prices.

This module does NOT send on its own. It renders every recipient's email to a
review HTML for Will to approve; sending stays the gated step in fpf_send.py
(reusing tracked_send) once approved.

Usage:
  python3 scripts/fpf_personalize.py --preview   # render all recipients -> review HTML
  python3 scripts/fpf_personalize.py --send [--dry-run]   # send (after approval)
"""
import os, sys, re, json, argparse
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv("/home/fields/Fields_Orchestrator/.env")
from shared.db import get_client
import five_property_friday as fpf
import fpf_send as S

SUB_KEY_FROM_SLUGWORD = {"robina": "robina", "burleigh-waters": "burleigh_waters",
                         "burleigh_waters": "burleigh_waters", "varsity-lakes": "varsity_lakes",
                         "varsity_lakes": "varsity_lakes"}


def _crm(email):
    return get_client()["system_monitor"]["crm_contacts"].find_one(
        {"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}}) or {}


def _first_name(name):
    """Return a clean first name or None. Conservative: real given-name only."""
    if not name:
        return None
    tok = str(name).strip().split()
    if not tok:
        return None
    fn = tok[0]
    if not re.fullmatch(r"[A-Za-z][A-Za-z'\-]{1,19}", fn):
        return None
    return fn[:1].upper() + fn[1:]


def _slug_of(path):
    m = re.match(r"/property/([^/?%]+)", path or "")
    return m.group(1) if m else None


def _suburb_of_news(path):
    m = re.search(r"/(?:news|market-intelligence)/([a-zA-Z\-]+)", path or "")
    if not m:
        return None
    return SUB_KEY_FROM_SLUGWORD.get(m.group(1).lower())


def _live_property(slug):
    """The still-for_sale doc for this url_slug, else None. Also returns current
    status when not live (so we never feature a sold/withdrawn home)."""
    gc = get_client()["Gold_Coast"]
    for coll in fpf.SUBURB_COLLECTIONS:
        d = gc[coll].find_one({"url_slug": slug, "listing_status": "for_sale"})
        if d:
            return d, coll, "for_sale"
    for coll in fpf.SUBURB_COLLECTIONS:
        d = gc[coll].find_one({"url_slug": slug}, {"listing_status": 1})
        if d:
            return None, coll, d.get("listing_status")
    return None, None, "not_found"


def _cand_from_doc(d, coll):
    """Build the same candidate dict fpf.gather() produces, for one doc."""
    vd = d.get("valuation_data") or {}
    conf = vd.get("confidence") or {}
    recon = conf.get("reconciled_valuation")
    rng = conf.get("range") or {}
    ask = fpf.parse_price(d.get("price") or d.get("display_price"))
    gap = ((ask - recon) / recon * 100) if (ask and recon) else None
    return {"address": d.get("address") or d.get("display_address"),
            "url_slug": d.get("url_slug"), "suburb": coll,
            "beds": d.get("bedrooms"), "baths": d.get("bathrooms"),
            "price_text": d.get("price") or d.get("display_price"),
            "ask": ask, "recon": recon, "lo": rng.get("low"), "hi": rng.get("high"),
            "conf": conf.get("confidence"), "dom": d.get("days_on_market"),
            "reduced": bool(d.get("price_history") or d.get("price_changes")), "gap": gap}


def _role_for_gap(c):
    g = c["gap"]
    if g is not None and c["lo"] and c["hi"]:
        if g < -3:
            return "Best value"
        if g > 8:
            return "Priced ahead of comps"
        return "Premium, priced right"
    return "One to watch"


def resolve(email, subs, beds, baths, src):
    """Enriched recipient profile."""
    crm = _crm(email)
    lb = crm.get("lead_brief") or {}
    lw = crm.get("lead_web") or {}
    pv = (lw.get("activity") or {}).get("pages_visited", [])

    viewed_live, viewed_dead, content_subs = [], [], {}
    for p in pv:
        path = p.get("path") or ""
        cnt = p.get("count", 1)
        if path.startswith("/property/"):
            slug = _slug_of(path)
            doc, coll, status = _live_property(slug) if slug else (None, None, None)
            if doc is not None:
                viewed_live.append((_cand_from_doc(doc, coll), cnt))
            elif coll:
                viewed_dead.append((slug, coll, status, cnt))
        else:
            sk = _suburb_of_news(path)
            if sk:
                content_subs[sk] = content_subs.get(sk, 0) + cnt

    # ---- which viewed homes are safe to surface / infer budget from ----
    # Exclude anything priced far off comps (|gap|>SANITY — e.g. a $3.3M home a
    # 3-bed seeker glanced at once) or well above the suburb median: a one-off
    # browse must not tout an out-of-comps home or blow the budget out.
    med_budget = S.budget_for(subs)

    def _surfaceable(c):
        if c["gap"] is not None and abs(c["gap"]) > fpf.SANITY_PCT:
            return False
        if c["ask"] and med_budget and c["ask"] > med_budget * 1.4:
            return False
        return True

    surfaceable_viewed = [(c, cnt) for c, cnt in viewed_live if _surfaceable(c)]

    # ---- infer a budget from the SURFACEABLE viewed asking prices ----
    viewed_prices = [c["ask"] for c, _ in surfaceable_viewed if c["ask"]]
    if viewed_prices:
        inferred = max(viewed_prices)
        budget = max(inferred, med_budget or 0) or None
        budget_basis = f"inferred from homes viewed (up to ${inferred:,})"
    else:
        budget = med_budget
        budget_basis = f"suburb median (${med_budget:,})" if med_budget else "unknown"

    # ---- suburb interest weighting (property + content views) ----
    interest = {s: 0 for s in subs}
    for c, cnt in viewed_live:
        if c["suburb"] in interest:
            interest[c["suburb"]] += 2 * cnt
    for slug, coll, status, cnt in viewed_dead:
        if coll in interest:
            interest[coll] += 1 * cnt
    for sk, cnt in content_subs.items():
        if sk in interest:
            interest[sk] += cnt
    subs_ranked = sorted(subs, key=lambda s: -interest.get(s, 0))

    return {
        "email": email, "src": src, "subs": subs, "subs_ranked": subs_ranked,
        "beds": beds, "baths": baths,
        "first_name": _first_name(crm.get("name")),
        "crm_name": crm.get("name"),
        "timeframe": lb.get("timeframe"), "owns": lb.get("owns_gc_home"),
        "viewed_live": viewed_live, "surfaceable_viewed": surfaceable_viewed,
        "viewed_dead": viewed_dead,
        "content_subs": content_subs, "interest": interest,
        "budget": budget, "budget_basis": budget_basis,
        "engaged": bool(pv),
    }


def personalized_picks(rec, cap=5):
    """Viewed-live homes first (roled by gap), then fill from the scored pool,
    ordered by suburb interest. Never pads with >1 no-gap filler."""
    picks, used_slugs = [], set()

    # 1) homes they actually viewed, still live AND in-range, best (most under
    #    comps) first, cap 2 so the email stays curation, not a replay.
    vlive = sorted(rec["surfaceable_viewed"],
                   key=lambda cc: (cc[0]["gap"] if cc[0]["gap"] is not None else 999))
    for c, cnt in vlive[:2]:
        # Surface silently — lead with homes they viewed, but NEVER say so.
        # The role is the ordinary comps role; nothing signals we tracked them.
        picks.append((_role_for_gap(c), c))
        used_slugs.add(c["url_slug"])

    # 2) fill from the standard scored curation, but drawn suburb-by-suburb in
    #    interest order so a Varsity-focused reader leads with Varsity, etc.
    budget = rec["budget"]
    remaining = cap - len(picks)
    if remaining > 0:
        pool = []
        for s in rec["subs_ranked"]:
            # beds/baths MUST be ints — Cosmos $gte against a string matches no
            # numeric value (BSON orders numbers below strings), silently zeroing
            # the fill pool. This is why unfixed lists showed only viewed homes.
            brief = {"suburbs": [s], "beds": S._int(rec["beds"]),
                     "baths": S._int(rec["baths"]), "budget": budget}
            cands = fpf.gather(brief)
            if budget:
                cands = [c for c in cands if not (c["ask"] and c["ask"] > budget * 1.25)]
            cands = [c for c in cands if c["url_slug"] not in used_slugs
                     and not (c["gap"] is not None and abs(c["gap"]) > fpf.SANITY_PCT)]
            cands.sort(key=lambda c: -fpf.score(c, budget))
            pool.extend(cands)
        # assign_roles gives distinct roles; run it on the interest-ordered pool
        extra = fpf.assign_roles(pool, budget)
        nogap_used = 0
        for role, c in extra:
            if len(picks) >= cap:
                break
            if c["url_slug"] in used_slugs:
                continue
            if c["gap"] is None:                 # no value story (Auction/EOI/Contact Agent)
                if nogap_used >= 2:              # allow a couple, never an all-filler email
                    continue
                nogap_used += 1
            used_slugs.add(c["url_slug"])
            picks.append((role, c))
    return picks[:cap]


# ---------------- copy ----------------
def _opening(rec, picks):
    """Neutral opener. We use their behaviour to CHOOSE and ORDER the homes, but
    the copy never reveals it — no "you've been looking at", no "you viewed".
    The only personal facts we reference are ones THEY told us on the form
    (their timeframe), never anything we observed on the site."""
    fn = rec["first_name"]
    hi = f"Hi {fn}," if fn else "Hi there,"
    subs_lbl = " / ".join(S.SUBURB_LABEL.get(s, s) for s in rec["subs_ranked"])
    n = len(picks)
    count_word = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}.get(n, str(n))
    plural = "home" if n == 1 else "homes"
    lines = [f"Here are {count_word} {plural} in {subs_lbl} worth your attention this week — "
             f"with the comparable-sales data behind each."]

    # timeframe tone — from THEIR stated brief, not from tracking (light, no advice)
    if rec["timeframe"] == "now":
        lines.append("You mentioned you're looking to move now, so we've leaned toward homes already on the market and open to offers.")
    elif rec["timeframe"] == "in_3_6_months":
        lines.append("No rush on your side over the next few months — this is as much to help you learn the market as to act on.")
    return hi, lines


def render_html(rec, picks):
    hi, lead_lines = _opening(rec, picks)
    subs_lbl = " / ".join(S.SUBURB_LABEL.get(s, s) for s in rec["subs_ranked"])
    rows = [f"<p>{hi}</p>"] + [f"<p>{l}</p>" for l in lead_lines]
    for i, (role, c) in enumerate(picks, 1):
        slug = c.get("url_slug") or re.sub(r",.*", "", c["address"]).strip().lower().replace(" ", "-")
        url = f"https://fieldsestate.com.au/property/{slug}"
        rows.append(
            f'<div style="margin:0 0 20px;padding-bottom:16px;border-bottom:1px solid #eee">'
            f'<p style="margin:0 0 4px"><b>{i}. {role} — {c["address"]}</b><br>'
            f'<span style="color:#666">{c["beds"]} bed / {c["baths"]} bath · asking {c["price_text"]}</span></p>'
            f'<p style="margin:0 0 6px">{fpf.take_line(role, c)}</p>'
            f'<p style="margin:0"><a href="{url}" style="color:#b87333">See the full analysis →</a></p></div>')
    # content link if they've been reading a suburb's coverage
    if rec["content_subs"]:
        sk = max(rec["content_subs"], key=rec["content_subs"].get)
        rows.append(f'<p>More on this market: '
                    f'<a href="https://fieldsestate.com.au/news/{sk.replace("_","-")}" style="color:#b87333">'
                    f'our latest {S.SUBURB_LABEL.get(sk, sk)} coverage →</a></p>')
    # owner soft hook — offering data, not advice (value framing per §5)
    if rec["owns"] == "yes":
        rows.append("<p>And since you already own on the Gold Coast: if you'd like our data-backed read on what your "
                    "current place is worth to help plan the move, just reply and we'll send it.</p>")
    rows.append("<p>Reply and tell us which to dig into — or send your budget and must-haves and we'll retune next Friday's list.</p>"
                "<p>— Will, Fields</p>")
    return S._wrap("".join(rows))


def subject_for(rec, picks=None):
    # Neutral subject — names their suburb(s), never references their browsing.
    subs_lbl = " / ".join(S.SUBURB_LABEL.get(s, s) for s in rec["subs_ranked"])
    return f"Your 5 for Friday — {subs_lbl}"


# ---------------- recipient roster (mirrors fpf_send.friday_batch selection) ----------------
def roster():
    sm = get_client()["system_monitor"]
    out = []
    seen = set()
    for lead in sm["fb_leads"].find({"form_id": {"$in": list(S.BUYER_BRIEF_FORMS)}, "fpf_status": "active"}):
        f = lead.get("fields", {}) or {}
        email = (f.get("email") or "").strip()
        subs = S.target_suburbs(f.get("area"))
        if not email or not subs or S.is_opted_out(email):
            continue
        seen.add(email.lower())
        out.append({"email": email, "subs": subs, "beds": f.get("bedrooms"),
                    "baths": f.get("bathrooms"), "src": "fb_lead", "ref": lead["_id"]})
    for sub in sm[S.WEBSITE_SUBS_COLL].find({"status": "active"}):
        email = (sub.get("email") or "").strip()
        if not email or email.lower() in seen or email == "will@fieldsestate.com.au":
            continue
        if S.is_opted_out(email):
            continue
        subs = S.website_sub_suburbs(sub)
        out.append({"email": email, "subs": subs, "beds": sub.get("bedrooms"),
                    "baths": sub.get("baths") or sub.get("bathrooms"), "src": "website",
                    "ref": sub.get("_id"), "last_shortlist_at": sub.get("last_shortlist_at")})
    for r in out:
        r.setdefault("last_shortlist_at", None)
    # fill last_shortlist_at for fb_leads (needed by the double-send guard)
    return out


def build_all():
    results = []
    sm = get_client()["system_monitor"]
    for r in roster():
        rec = resolve(r["email"], r["subs"], r["beds"], r["baths"], r["src"])
        rec["ref"] = r["ref"]                 # RAW _id (ObjectId/int) — never stringified
        if r["src"] == "fb_lead":
            lead = sm["fb_leads"].find_one({"_id": r["ref"]}, {"last_shortlist_at": 1})
            rec["last_shortlist_at"] = (lead or {}).get("last_shortlist_at")
        else:
            rec["last_shortlist_at"] = r.get("last_shortlist_at")
        picks = personalized_picks(rec)
        results.append((rec, picks))
    return results


def preview(path):
    results = build_all()
    cards = []
    for rec, picks in results:
        meta = (f"<div style='font:12px monospace;color:#555;background:#f6f6f6;padding:8px;margin:0 0 8px'>"
                f"<b>{rec['email']}</b> · src={rec['src']} · name={rec['crm_name']!r} → greet "
                f"{'Hi '+rec['first_name'] if rec['first_name'] else 'Hi there'} · "
                f"subs(interest-ordered)={rec['subs_ranked']} · beds≥{S._int(rec['beds'])} baths≥{S._int(rec['baths'])} · "
                f"budget={rec['budget_basis']} · timeframe={rec['timeframe']} · owns={rec['owns']} · "
                f"viewed_live={[c['address'].split(',')[0] for c,_ in rec['viewed_live']]} · "
                f"viewed_dead={[(s,st) for s,_,st,_ in rec['viewed_dead']]}</div>")
        cards.append(f"<section style='max-width:640px;margin:0 auto 40px;border:1px solid #ddd;border-radius:8px;padding:16px'>"
                     f"<div style='font:13px monospace;color:#b87333'>SUBJECT: {subject_for(rec)}</div>{meta}"
                     f"{render_html(rec, picks)}</section>")
    html = ("<h1 style='max-width:640px;margin:16px auto;font-family:sans-serif'>Five Property Friday — personalised preview "
            f"({len(results)} recipients) · {datetime.now(S.AEST):%a %d %b %H:%M AEST}</h1>" + "".join(cards))
    open(path, "w").write(html)
    print(f"wrote {path} — {len(results)} recipients")
    return results


def send_all(dry=False):
    """Send the personalised batch. Mirrors fpf_send stamping + failure reporting."""
    sm = get_client()["system_monitor"]
    today = datetime.now(S.AEST).date().isoformat()
    results = build_all()
    sent, failed, skipped = [], [], 0
    for rec, picks in results:
        if not picks:
            continue
        # same-day double-send guard (mirrors fpf_send.friday_batch)
        if not dry and S._aest_date(rec.get("last_shortlist_at")) == today:
            skipped += 1
            print(f"  SKIP (already sent today) -> {rec['email']}")
            continue
        r = S.tracked_send(rec["email"], subject_for(rec, picks), render_html(rec, picks),
                           "fpf_shortlist",
                           {"ref": str(rec["ref"]), "src": rec["src"], "count": len(picks),
                            "personalised": True}, dry)
        if dry or r.get("ok"):
            sent.append(rec["email"])
            if not dry:
                now = datetime.now(timezone.utc).isoformat()
                coll = "fb_leads" if rec["src"] == "fb_lead" else S.WEBSITE_SUBS_COLL
                sm[coll].update_one({"_id": rec["ref"]},   # RAW _id from roster()
                                    {"$set": {"last_shortlist_at": now, "last_shortlist_send": r.get("send_id")}})
            print(f"  {'[DRY] ' if dry else ''}sent -> {rec['email']}")
        else:
            failed.append((rec["email"], r.get("error", "unknown")))
            print(f"  FAILED -> {rec['email']}: {r.get('error')}")
    print(f"\npersonalised batch: {len(sent)} sent, {len(failed)} failed, {skipped} skipped")
    if not dry:
        S._report_batch(sent, failed, 0, dry)
    return sent, failed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default="/tmp/claude-1001/-home-fields-Fields-Orchestrator/f1694ada-0d66-4689-89a2-0c2e57b35933/scratchpad/fpf_preview.html")
    args = ap.parse_args()
    if args.preview:
        preview(args.out)
    elif args.send:
        send_all(dry=args.dry_run)
    else:
        sys.exit("--preview or --send")


if __name__ == "__main__":
    main()
