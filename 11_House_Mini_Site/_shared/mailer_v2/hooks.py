#!/usr/bin/env python3
"""
hooks.py — the V2 finding-selection engine.

V1 printed the same three statistics on every mailer: competitors, comparable
sales, distance to the nearest school. Two of those are *inputs* — they show the
machinery ran. Only the first is a *finding* — it says something about this house
that its owner does not already know.

V2 builds every finding the report can honestly support, scores each one, and
lets the best one lead. A finding earns its place on the page by five measures:

  specificity  is this unmistakably about THIS house, not the suburb?
  surprise     would the owner be unable to guess it?
  relevance    does it bear on value, desirability or sale position?
  curiosity    does knowing half of it make you need the other half?
  credibility  can we defend the claim if the owner interrogates it?

`curiosity` is the one V1 had no concept of, and it is the one that decides
whether a mailer gets scanned. "1.24 km to Arcadia College" scores well on
specificity and credibility and close to zero on curiosity: it answers itself.
"Only 5 of 206 homes genuinely compete with yours" withholds the five.

The owner already knows their own house. They do not know where it sits. Every
finding here is therefore RELATIVE — against the competing set, the cohort, or
the local sales record — never a bare property fact.

Nothing in this file invents data. Each builder reads named fields off the
report doc and returns None when they are absent, so a thin report simply has
fewer candidates rather than a confident-sounding blank.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# scoring weights. curiosity is weighted hardest because the mailer has exactly
# one job — earn the scan — and credibility is weighted second because a claim
# we cannot defend costs more than a scan is worth.
# ---------------------------------------------------------------------------
WEIGHTS = {
    "curiosity": 3.0,
    "credibility": 2.5,
    "specificity": 2.0,
    "relevance": 2.0,
    "surprise": 1.5,
}


@dataclass
class Finding:
    """One candidate statement about the property.

    `number` / `unit` / `label` render as a card. `sub` is the supporting line.
    `hero_headline` is only used when this finding leads page 1 — it is the
    full sentence, and it must withhold the answer.
    """
    kind: str
    number: str
    label: str
    sub: str
    hero_headline: Optional[str] = None
    hero_consequence: Optional[str] = None
    unit: str = ""
    # scores, 0-10
    specificity: int = 0
    surprise: int = 0
    relevance: int = 0
    curiosity: int = 0
    credibility: int = 0
    # findings that must not appear alongside this one (see CONFLICTS)
    conflicts: tuple = ()
    # only these may lead the page; a finding without a hero_headline cannot
    hero_ok: bool = False

    @property
    def score(self) -> float:
        return sum(WEIGHTS[k] * getattr(self, k) for k in WEIGHTS)


# ---------------------------------------------------------------------------
# Findings that must never share a page.
#
# `competition` says "5 of 206 genuinely compete". `scarcity` says "29 of 191
# share your feature combination". Both are true and they measure different
# things, but printed side by side against near-identical denominators a
# five-second reader sees a contradiction — "is it 5 or 29?" — and trusts
# neither. This was a real defect in the V1 output. The rule below makes it
# structurally impossible rather than relying on whoever writes the copy next
# to remember.
# ---------------------------------------------------------------------------
CONFLICTS = {
    "competition": ("scarcity", "no_competition"),
    "no_competition": ("scarcity", "competition"),
    "scarcity": ("competition", "no_competition"),
    # both quantify the same feature's rarity from different angles
    "land_rank": ("feature_rarity",),
    "feature_rarity": ("land_rank",),
}


def _g(d: Any, *path, default=None):
    """Nested get that survives None and non-dicts at any depth."""
    cur = d
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return default if cur is None else cur


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


# ---------------------------------------------------------------------------
# finding builders — each returns a Finding or None
# ---------------------------------------------------------------------------

def _funnel(doc):
    """(close, in_band, total) — the competitive funnel, widest to narrowest.

    `close` is `funnel.close_tier` (`n_close` in competitor_matcher.py): every
    candidate in the band scoring within CLOSE_MATCH_THRESHOLD and surviving the
    price guard. It is computed over the FULL candidate set.

    It is emphatically NOT `len(comparables.closest_active)`, which V1 used for
    this headline. That array is `min(active_in_band, 6)` — a cap on how many
    substitutes get plotted on the map (TARGET_MAX in competitor_matcher.py,
    applied a second time as a literal `active[:6]` in comparable_feed.py). It
    came out as 6 for 23 of the 25 mailable addresses because it saturates, not
    because those homes each had six competitors. Printing it as "only 6 of 244
    genuinely compete" promotes a display limit to an analytical finding, and it
    was wrong in both directions: 26 Ballyliffen's mailer claimed 5 where the
    real close count is 7, and 22 Mapleton would have claimed 6 where it is 0.
    """
    f = _g(doc, "slots", "competitor_map", "ranked_comparison", "funnel", default={}) or {}
    close = f.get("close_tier")
    in_band = _g(doc, "comparables", "active_in_band") or f.get("in_band")
    total = _g(doc, "scarcity_features", "active_listings_total") or f.get("active_total")
    return close, in_band, total


def f_competition(doc) -> Optional[Finding]:
    """A small closely-competing set inside a large reviewed set.

    Scored on the actual ratio: 1 of 220 is a far better hook than 13 of 226,
    and V1's fixed scores could not tell them apart.
    """
    close, in_band, total = _funnel(doc)
    if close is None or not total or close < 1 or close >= total:
        return None
    pct = 100 * close / total
    # the scarcer the competition, the more startling the finding
    surprise = 10 if pct < 1 else 9 if pct < 2 else 8 if pct < 4 else 6
    band_note = (f"narrowed from {in_band} in your home&rsquo;s size and type band"
                 if in_band else "narrowed from the local search area")
    return Finding(
        kind="competition",
        number=str(close),
        label=f"{_plural(close, 'Home', 'Homes')} for sale that closely compete with yours",
        sub=f"{band_note}, out of {total} homes for sale across your area",
        hero_headline=(f"Of the {total} homes for sale near you, only <b>{close}</b> "
                       f"closely {_plural(close, 'competes', 'compete')} with yours."),
        hero_consequence=(
            "Those are the homes a buyer weighs yours against when deciding "
            "whether it is fairly priced &mdash; or worth stretching for."
        ),
        specificity=10, surprise=surprise, relevance=10, curiosity=10, credibility=9,
        conflicts=CONFLICTS["competition"], hero_ok=True,
    )


def f_no_competition(doc) -> Optional[Finding]:
    """Nothing closely competes — the strongest hook the data ever produces.

    Six of the 25 mailable addresses are in this position. V1 could not express
    it at all: capped at six plotted substitutes, it would have printed "only 6
    of 244 genuinely compete" for a home with no close competition whatsoever.
    """
    close, in_band, total = _funnel(doc)
    if close != 0 or not total:
        return None
    band_note = (f"we compared it against {in_band} homes in its size and type band"
                 if in_band else "we compared it against the local search area")
    return Finding(
        kind="no_competition",
        number="0",
        label="Homes for sale that closely compete with yours",
        sub=f"{band_note}, drawn from {total} for sale across your area",
        hero_headline=(f"We checked {total} homes for sale near you. "
                       f"<b>None</b> of them closely competes with yours."),
        hero_consequence=(
            "That is unusual, and it cuts both ways: less to be measured "
            "against, and fewer recent results to anchor a buyer&rsquo;s "
            "expectations. Both matter to how a home should be priced."
        ),
        specificity=10, surprise=10, relevance=10, curiosity=10, credibility=8,
        conflicts=CONFLICTS["competition"], hero_ok=True,
    )


def f_advantages_tradeoffs(doc) -> Optional[Finding]:
    """Named strengths AND named trade-offs.

    The trade-off half is the reason this scores so highly. Every other piece of
    mail the owner receives tells them their home is wonderful, so they discount
    all of it. A sender willing to say "two things buyers may weigh against it"
    is read as an assessment rather than an approach — and the negative is a
    stronger open loop than the positive, because nobody can leave "what's wrong
    with my house?" unanswered.

    We never print WHICH. The count is the hook; the answer is behind the QR.
    """
    adv = _g(doc, "scarcity_features", "notable_features", default=[]) or []
    trades = _g(doc, "positioning", "tradeOffs", default=[]) or []
    n_adv, n_tr = len(adv), len(trades)
    if not n_adv or not n_tr:
        return None
    return Finding(
        kind="advantages_tradeoffs",
        number=f"{n_adv}&thinsp;/&thinsp;{n_tr}",
        label="Strengths, and trade-offs, identified",
        sub=(f"{n_adv} {_plural(n_adv, 'thing', 'things')} working in your home's favour "
             f"&mdash; and {n_tr} {_plural(n_tr, 'a buyer', 'buyers')} may weigh against it"),
        hero_headline=(f"We found <b>{n_adv}</b> {_plural(n_adv, 'thing', 'things')} working in "
                       f"your home's favour &mdash; and <b>{n_tr}</b> buyers may weigh against it."),
        hero_consequence=(
            "Both matter to what a buyer will pay. We have named them plainly "
            "rather than listing only the flattering half."
        ),
        # a lopsided split is a duller finding than a balanced one — "8 strengths
        # and 1 trade-off" reads as marketing, "3 and 3" reads as an assessment
        surprise=9 if min(n_adv, n_tr) >= 2 else 7,
        specificity=9, relevance=9, curiosity=10, credibility=8,
        hero_ok=True,
    )


def f_scarcity(doc) -> Optional[Finding]:
    """How rare the full feature combination is across the active market.

    Deliberately worded to be unmistakably a DIFFERENT test from `competition`
    — "share the combination" vs "genuinely compete" — because the two numbers
    otherwise read as a contradiction. Even so, CONFLICTS keeps them apart.
    """
    po = doc.get("positioning_object") or {}
    if po.get("scarcity_verdict") != "uncommon_combination":
        return None
    matching = _g(po, "scarcity_receipt", "matching")
    total = _g(po, "scarcity_receipt", "total")
    if not matching or not total or matching >= total:
        return None
    pct = round(100 * matching / total)
    return Finding(
        kind="scarcity",
        number=f"{matching} in {total}",
        label="Share your home's full feature combination",
        sub=(f"only {pct}% of homes for sale locally offer the same combination "
             f"&mdash; a broader test than direct competition"),
        hero_headline=(f"Just <b>{matching}</b> of {total} homes for sale locally offer "
                       f"your home's combination of features."),
        hero_consequence=(
            "Scarcity only pays when a buyer is looking for exactly that "
            "combination. We have worked out who is."
        ),
        # rarity is the whole point of this finding, so it drives the score
        surprise=10 if pct <= 2 else 9 if pct <= 5 else 7 if pct <= 15 else 5,
        curiosity=9 if pct <= 5 else 7,
        specificity=9, relevance=8, credibility=8,
        conflicts=CONFLICTS["scarcity"], hero_ok=True,
    )


def f_buyer(doc) -> Optional[Finding]:
    """One buyer group stands out.

    V1 printed the persona's description on page 2, which answered the question
    and removed the reason to scan. V2 prints only that the answer exists.
    """
    personas = _g(doc, "positioning", "personas", default=[]) or []
    lead = next((p for p in personas if isinstance(p, dict) and p.get("brief")), None)
    if not lead:
        return None
    # a persona is only interesting if we can say why they'd pay more
    depth = 9 if lead.get("paysMoreFor") else 7
    return Finding(
        kind="buyer",
        number="1",
        label="Buyer group is the strongest fit",
        sub="identified from who is actually buying homes like yours nearby",
        hero_headline="<b>One</b> buyer group stands out as the strongest fit for your home.",
        hero_consequence=(
            "Not &ldquo;families&rdquo; &mdash; a specific group, and the "
            "particular thing about your home they pay more for."
        ),
        specificity=8, surprise=7, relevance=9, curiosity=depth, credibility=7,
        hero_ok=True,
    )


def f_land_rank(doc) -> Optional[Finding]:
    """Land size against the cohort median — a relative fact, not a property fact.

    The owner knows their block is 879 m². What they cannot know is that the
    homes theirs is measured against run to a 662 m² median.

    We state the two medians rather than a percentile. `cohort_stats` carries a
    median and a sample size but not a distribution, so any "larger than 84% of"
    claim would be fabricated precision — and it is exactly the sort of number
    an owner would ask us to justify.
    """
    land = _g(doc, "scarcity_features", "features_basic_snapshot", "land_size_sqm")
    median = _g(doc, "scarcity_features", "cohort_stats", "land_size_sqm_median")
    n = _g(doc, "scarcity_features", "cohort_stats", "n")
    if not land or not median or not n or n < 20:
        return None
    ratio = land / median
    if ratio < 1.15:            # only remarkable when clearly above the middle
        return None
    pct_more = round(100 * (ratio - 1))
    return Finding(
        kind="land_rank",
        number=f"{int(land)}",
        unit="m&sup2;",
        # Both lines are kept deliberately short. A four-digit land figure plus
        # its unit already consumes most of a support card's first line, and a
        # three-line sub underneath it clips against the card bounds — which is
        # invisible in the PDF until the artwork verifier reads it back.
        label=f"Of land &mdash; {pct_more}% above the local median",
        sub=f"across {int(n)} comparable homes",
        hero_headline=(f"Your block is <b>{pct_more}% larger</b> than the typical home "
                       f"yours is measured against."),
        hero_consequence=(
            "Land is the part of a home that cannot be added later, and in this "
            "cohort it is one of the differences that separates sale results."
        ),
        # a 5.7x block is a genuine story; a 1.2x block is a supporting detail
        surprise=10 if ratio >= 2.0 else 8 if ratio >= 1.5 else 6,
        curiosity=7 if ratio >= 1.5 else 5,
        specificity=9, relevance=8, credibility=9,
        conflicts=CONFLICTS["land_rank"],
        hero_ok=ratio >= 1.5,
    )


def f_feature_rarity(doc) -> Optional[Finding]:
    """A feature that is both uncommon locally and shows up in the sales record.

    We print the PREVALENCE (a plain frequency, unarguable) and not the price
    premium. The stored `premium_pct` is a raw median gap between homes with and
    without the feature; the same record's `like_for_like_pct` is typically far
    smaller, because most of the headline gap is the company the feature keeps
    — bigger blocks sit with bigger houses in better streets. Printing 13.6%
    when the defensible figure is 3.8% would be the kind of claim that loses an
    owner's trust the moment they ask how it was derived.
    """
    prems = _g(doc, "scarcity_features", "cohort_premiums", default=[]) or []
    best = None
    for p in prems:
        if not p.get("reliable") or p.get("classification") != "price_driver":
            continue
        prev = p.get("prevalence_pct")
        if prev is None or prev >= 50:      # not rare enough to be interesting
            continue
        if best is None or prev < best.get("prevalence_pct", 100):
            best = p
    if not best:
        return None
    prev = best["prevalence_pct"]
    label = (best.get("feature_label") or "one feature").strip()
    in_ten = round(prev / 10)
    freq = f"{in_ten} in 10" if 1 <= in_ten <= 9 else f"{prev:.0f}%"
    return Finding(
        kind="feature_rarity",
        number=freq,
        label=f"Comparable homes offer {label.lower()}",
        sub="one of the features separating local sale results &mdash; and yours has it",
        surprise=9 if prev <= 20 else 7,
        specificity=8, relevance=8, curiosity=6, credibility=8,
        conflicts=CONFLICTS["feature_rarity"],
    )


def f_recent_activity(doc) -> Optional[Finding]:
    """Something changed in the competing set recently. Time-sensitive = urgent."""
    acts = doc.get("activity") or []
    rel = [a for a in acts if a.get("kind") in ("new_listing", "sold", "price_change")
           and a.get("date")]
    if not rel:
        return None
    rel.sort(key=lambda a: a["date"], reverse=True)
    latest = rel[0]
    try:
        d = datetime.fromisoformat(str(latest["date"])[:10]).replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - d).days
    except Exception:
        return None
    if days < 0 or days > 30:               # stale news is not news
        return None
    kind_word = {"new_listing": "came to market",
                 "sold": "sold",
                 "price_change": "changed price"}[latest["kind"]]
    when = "today" if days == 0 else ("yesterday" if days == 1 else f"{days} days ago")
    return Finding(
        kind="recent_activity",
        number=str(len(rel)),
        label="Changes logged in your competing set",
        sub=f"most recently, a comparable home {kind_word} {when} &mdash; checked nightly",
        specificity=8, surprise=6, relevance=7, curiosity=6, credibility=9,
    )


def f_school_walk(doc) -> Optional[Finding]:
    """Proximity — permitted ONLY when it is genuinely remarkable.

    V1 gave this a fixed third slot on every mailer, which is why one house got
    "477 m walk to Robina State School" (legitimately a selling point) and
    another got "1,634 m to Robina State School" (a number, not a finding).
    Distance qualifies here only as a real walk that the report itself has
    flagged as an advantage; otherwise a better finding takes the slot.
    """
    pois = doc.get("pois") or []
    school = next((p for p in pois if p.get("category") == "school" and p.get("walkMetres")), None)
    if not school:
        return None
    m = int(school["walkMetres"])
    flags = _g(doc, "positioning_object", "evidence", "flags", default={}) or {}
    if m > 600 or not (flags.get("veryStrongSchoolWalk") or flags.get("schoolWalkAdvantage")):
        return None
    return Finding(
        kind="school_walk",
        number=str(m),
        unit="m",
        label=f"On foot to {school.get('name')}",
        sub="measured along the walking route, not a straight line &mdash; close enough to matter to a buyer with children",
        specificity=9, surprise=5, relevance=7, curiosity=3, credibility=10,
    )


BUILDERS: tuple[Callable, ...] = (
    f_competition,
    f_no_competition,
    f_advantages_tradeoffs,
    f_scarcity,
    f_buyer,
    f_land_rank,
    f_feature_rarity,
    f_recent_activity,
    f_school_walk,
)


def build_findings(doc) -> list[Finding]:
    """Every finding this report can honestly support, best first."""
    out = []
    for b in BUILDERS:
        try:
            f = b(doc)
        except Exception:
            f = None            # a malformed sub-document costs one candidate, not the mailer
        if f:
            out.append(f)
    out.sort(key=lambda f: f.score, reverse=True)
    return out


def select(doc, n_support: int = 2):
    """Pick the finding that leads, plus `n_support` that corroborate it.

    Returns (hero, [supporting...], [all candidates]). Raises when nothing
    hero-worthy exists — a mailer with no finding is a leaflet, and we would
    rather print nothing than fall back to "1.24 km to a school".
    """
    cands = build_findings(doc)
    hero = next((f for f in cands if f.hero_ok), None)
    if hero is None:
        raise ValueError(
            "no hero-grade finding available (need competition, strengths+trade-offs, "
            "scarcity or buyer fit)")

    blocked = set(hero.conflicts)
    support = []
    for f in cands:
        if f is hero or f.kind in blocked:
            continue
        support.append(f)
        blocked |= set(f.conflicts)
        if len(support) == n_support:
            break
    return hero, support, cands
