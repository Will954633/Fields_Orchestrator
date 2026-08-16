#!/usr/bin/env python3
"""Rule 5 editorial gate — run over an article BODY, not just its headline.

Why this exists
---------------
A Rule 5 checker already lived inside ``fb_post_article.py``, but it was only ever
handed the composed Facebook post — a title plus a one-line excerpt. Nothing had ever
read the article bodies. On 2026-08-13 a body-level scan of the 73 published articles
found a live "Practical Application" section instructing readers to "Start your
property search now", "consider listing sooner rather than later" and "Make
buy/hold/sell decision" — none of which the headline gate could ever have seen,
because it was never shown the paragraph they sit in.

So the patterns below are the ones from ``fb_post_article`` (kept in sync deliberately)
plus the body-only constructs that surfaced in that scan. Import ``check_text`` from
here rather than re-deriving a pattern list; a second divergent copy of these rules is
how the first gap happened.

Usage
-----
    python3 scripts/editorial_gate.py --published        # scan live articles
    python3 scripts/editorial_gate.py --drafts           # scan drafts
    python3 scripts/editorial_gate.py --slug <slug>      # one article
    python3 scripts/editorial_gate.py --all --quiet      # exit 1 if any breach

Programmatic:
    from editorial_gate import check_article
    breaches = check_article(doc)          # [] means clean
"""

from __future__ import annotations

import argparse
import html as htmllib
import re
import sys

FORBIDDEN_WORDS = ["stunning", "nestled", "boasting", "rare opportunity", "robust market"]

# ── No advice — never tell the reader what to do ─────────────────────────
ADVICE_PATTERNS = [
    (r"\byou should\b", "tells the reader what to do"),
    (r"\byou need to\b", "tells the reader what to do"),
    (r"\byou must\b", "tells the reader what to do"),
    (r"\bconsider (?:buying|selling|listing)\b", "advises a course of action"),
    (r"\bnow is (?:a good|the) time\b", "advises timing"),
    (r"\bnow'?s the time\b", "advises timing"),
    (r"\b(?:don'?t|do not) (?:wait|miss|hesitate)\b", "advises a course of action"),
    (r"\bact (?:now|fast)\b", "advises a course of action"),
    (r"\bwe recommend\b", "gives advice"),
    (r"\bthe smart move\b", "gives advice"),
    # ── body-only constructs (added 2026-08-13 after the first body-level scan) ──
    (r"\bstart your (?:property )?search\b", "instructs the reader to act"),
    (r"\bsell into strength\b", "advises a course of action"),
    (r"\bstrong buy signal\b", "frames data as a trade instruction"),
    (r"\bbuy/hold/sell decision\b", "instructs the reader to transact"),
    (r"\bmake (?:a |your )?(?:buy|sell|purchase) decision\b", "instructs the reader to transact"),
    (r"\bhere'?s how to (?:actually )?use this\b", "frames analysis as instructions"),
    (r"\bwhat (?:you|we) should do\b", "tells the reader what to do"),
    (r"\bexercise caution\b", "advises a course of action"),
    (r"\bnegotiate harder\b", "advises a course of action"),
    (r"\byour (?:best|next) move\b", "advises a course of action"),
    (r"^\s*(?:step\s*\d+\s*:\s*)?(?:act|buy|sell|list|wait|watch out)\b", "imperative instruction"),
    # ── the HEDGED advisory register (added 2026-08-16) ──────────────────
    # Every pattern above catches an imperative. None of them caught the register the
    # "Is Now a Good Time to …?" series is actually written in: a weighed, two-sided
    # recommendation delivered as a verdict. The gate reported 90/90 clean while a live
    # page carried "The case for selling now / The case for waiting" under a heading
    # called "The Honest Answer", and closed by telling readers who "can afford to hold"
    # that they "may benefit". Hedging the verb does not stop it being advice — Rule 5
    # says the reader draws the conclusion, and a section that draws it for them breaches
    # it however softly it is phrased. See fix-history 2026-08-16 [ARTICLE-HEDGED-ADVICE].
    (r"\bthe case for (?:selling|buying|waiting|listing|holding)\b",
     "presents a recommendation for a course of action"),
    (r"\breasons to (?:buy|sell|list|wait|hold)\b", "presents a recommendation"),
    (r"\bthe honest answer\b", "delivers a verdict on what the reader should do"),
    # "buyers should not assume X is a firm date" cautions against over-reading a fact.
    # That is the opposite of advice and Rule 5 wants it, so exclude the negated forms.
    (r"\b(?:sellers?|buyers?|owners?)\s+should(?!\s+not\s+(?:assume|expect|read|infer|treat))\b",
     "tells the reader what to do"),
    (r"\bif you can afford to (?:hold|wait)\b", "advises timing"),
    (r"\b(?:sellers?|buyers?|owners?|you)\s+who\s+can\s+(?:hold|wait)\b", "advises timing"),
    (r"\bcompounds the case\b", "argues a course of action"),
    (r"\brewards?\s+(?:patience|action|waiting)\b", "advises a course of action"),
    (r"\bworth considering seriously\b", "advises a course of action"),
    (r"\btiming logic\b", "endorses the timing of a transaction"),
]

# ── No predictions — report indicators, never forecast ───────────────────
PREDICTION_PATTERNS = [
    (r"\bprices will\b", "predicts prices"),
    (r"\bwill (?:rise|fall|climb|drop|surge|crash|hold|keep rising|keep falling|continue to)\b",
     "predicts a move"),
    (r"\bis (?:set|poised|expected) to\b", "predicts a move"),
    (r"\bwe expect\b", "predicts"),
    (r"\bforecast(?:s|ing)?\b", "predicts"),
    (r"\bby (?:the end of|next) (?:year|quarter)[^.]{0,40}\bwill\b", "predicts"),
    (r"\blikely to (?:rise|fall|strengthen|soften|climb|drop)\b", "predicts a move"),
    (r"\bpredicts? (?:house |property )?prices\b", "predicts prices"),
    # ── hedged forecasts (added 2026-08-16, same scan as the advisory register) ──
    (r"\bmay (?:benefit|support (?:further|price)|see further)\b", "forecasts, hedged"),
    (r"\bgrounds for optimism\b", "forecasts sentiment about future prices"),
    (r"\bwhere prices land in \d{4}\b", "forecasts a price level for a named year"),
    (r"\bwill keep (?:increasing|rising|growing|climbing|falling)\b", "predicts a move"),
]

SHORTHAND_PRICE_RE = re.compile(r"\$\s*(\d+(?:\.\d+)?)\s*([mMkK])\b")

# Rule 5's number format is about PROPERTY prices. A development's build cost or a rail
# budget ("$5.75B of rail improvements", "$450M tower") is not a property price, and
# spelling it out in full would be absurd rather than clearer. No residential sale in our
# market approaches $20,000,000, so that is a safe dividing line.
PROJECT_SCALE_FLOOR = 20_000_000

# "not a forecast", "rather than a forecast", "is not predictive" — a sentence that
# DISCLAIMS a prediction must not be flagged as making one. This class was the single
# largest source of false positives on the first body-level scan.
NEGATION_RE = re.compile(
    r"\b(?:not|never|rather than|isn'?t|aren'?t|doesn'?t|don'?t|no)\b[^.]{0,60}$",
    re.IGNORECASE,
)

SUBURBS = [
    "Robina", "Burleigh Waters", "Burleigh Heads", "Varsity Lakes", "Mermaid Waters",
    "Miami", "Palm Beach", "Broadbeach", "Surfers Paradise", "Mudgeeraba", "Nerang",
    "Reedy Creek", "Clear Island Waters", "Gold Coast",
]

URL_RE = re.compile(r"https?://\S+")
# Base64 data URIs — charts are inlined as images and would otherwise dominate every scan.
DATA_URI_RE = re.compile(r"data:[a-z/+.-]+;base64,[A-Za-z0-9+/=]+")


def html_to_text(fragment: str) -> str:
    """Strip an HTML fragment to plain text."""
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", fragment or "")
    text = DATA_URI_RE.sub(" ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|h[1-6]|tr)>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = htmllib.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def _context(text: str, start: int, end: int, pad: int = 90) -> str:
    return text[max(0, start - pad):end + pad].replace("\n", " ").strip()


def check_text(text: str, *, check_suburb_case: bool = True) -> list[str]:
    """Return a list of Rule 5 breaches. An empty list means clean."""
    text = URL_RE.sub(" ", text)
    breaches: list[str] = []
    lowered = text.lower()

    for word in FORBIDDEN_WORDS:
        if re.search(r"\b" + re.escape(word) + r"\b", lowered):
            breaches.append(f'forbidden word: "{word}"')

    for pattern, why in ADVICE_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
            breaches.append(
                f'no-advice: "{m.group(0)}" — {why}\n      … {_context(text, m.start(), m.end())}'
            )

    for pattern, why in PREDICTION_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            # Skip a match that the same sentence explicitly disclaims.
            if NEGATION_RE.search(text[max(0, m.start() - 80):m.start()]):
                continue
            breaches.append(
                f'no-prediction: "{m.group(0)}" — {why}\n      … {_context(text, m.start(), m.end())}'
            )

    for m in SHORTHAND_PRICE_RE.finditer(text):
        value = float(m.group(1)) * (1_000_000 if m.group(2).lower() == "m" else 1_000)
        if value >= PROJECT_SCALE_FLOOR:
            continue  # development / infrastructure cost, not a property price
        breaches.append(
            f'number format: "{m.group(0)}" — use the full figure ($1,250,000), not shorthand'
            f'\n      … {_context(text, m.start(), m.end(), 60)}'
        )

    if check_suburb_case:
        for suburb in SUBURBS:
            if re.search(r"(?<![\w-])" + re.escape(suburb.lower()) + r"(?![\w-])", text):
                breaches.append(f'suburb not capitalised: "{suburb.lower()}" should be "{suburb}"')

    return breaches


# ── Acknowledged false positives ─────────────────────────────────────────
# A gate that always reports the same seven breaches is a gate everyone learns to ignore,
# and the next REAL breach lands in the noise. Each entry below was read in full context
# on 2026-08-13 and judged compliant; the reason is recorded so a later reader can
# disagree with the judgement rather than merely inherit it. Keyed on (slug, phrase).
ACKNOWLEDGED = {
    ("699d7217a47edd0001e07791", "is expected to"):
        "attributed to the development's own impact assessment, and about golf tourism, not prices",
    ("699d7222a47edd0001e077e1", "Forecasting"):
        "appears inside a cited source title (KPMG SEQ Economic Forecasting Update)",
    ("699d7224a47edd0001e077ef", "negotiate harder"):
        "describes what high-performing agents do; not an instruction to the reader",
    ("is-now-a-good-time-to-sell-in-robina", "you need to"):
        "idiom 'most of what you need to know'; not a directive to act",
    ("what-drives-gold-coast-house-prices", "Prices will"):
        "quotes a misconception the next line refutes",
    ("what-drives-gold-coast-house-prices", "will rise"):
        "quotes a misconception the next line refutes",
    ("leading-vs-lagging-indicators", "forecasts"):
        "describes what bank economists discuss; not our forecast",
    ("dom-three-week-sweet-spot", "predicts prices"):
        "defines what hedonic regression is as a method",
    # Drafts — the grammatical subject of "don't wait" is the PROPERTY, not the reader.
    # The pattern was written for "Don't wait to sell"; "the fairly-priced ones don't wait
    # long" is a description of market behaviour, which Rule 5 permits.
    ("sold-for-855-000-a-robina-duplex-that-opened-the-door-below-the-median", "don't wait"):
        "subject is the property, not the reader; describes market behaviour",
    ("sold-in-10-days-how-31-roundelay-drive-cleared-1-380-000-off-an-auction-campaign", "don't wait"):
        "subject is the property, not the reader; describes market behaviour",
    ("in-robina-three-bedroom-houses-sell-in-about-28-days-this-waterfront-one-just-listed",
     "prices will"):
        "'where this one prices' uses price as a verb; awkward but not a price forecast",
    ("in-robina-three-bedroom-houses-sell-in-about-28-days-this-waterfront-one-just-listed",
     "is set to"):
        "'priced to meet the market', not 'poised to'",
    # ── added 2026-08-16 with the hedged-advisory patterns ───────────────
    # "The honest answer" is a breach when it delivers a buy/sell verdict, which is how
    # the "Is Now a Good Time to …?" series uses it. These two use the same words to
    # answer an ANALYTICAL question — is migration still a driver, what does the Olympics
    # actually fund — and recommend no course of action to anyone. Read in full and
    # judged compliant; if a later reader disagrees, the sentence is quoted above.
    ("699d7222a47edd0001e077e1", "The honest answer"):
        "answers 'is the migration effect still working' analytically; recommends no action",
    ("699d7218a47edd0001e07798", "The honest answer"):
        "answers what the Olympics funds; about infrastructure causation, not a transaction",
}


def _is_acknowledged(key: str, breach: str) -> bool:
    for (slug, phrase), _reason in ACKNOWLEDGED.items():
        if slug == key and f'"{phrase}"' in breach:
            return True
    return False


def article_text(doc: dict) -> str:
    """The full readable text of an article — title plus body, in whichever field it lives."""
    body = doc.get("html") or doc.get("body") or doc.get("markdown") or doc.get("content") or ""
    return (doc.get("title") or "") + "\n" + html_to_text(body)


def check_article(doc: dict) -> list[str]:
    return check_text(article_text(doc))


def main() -> int:
    ap = argparse.ArgumentParser(description="Rule 5 editorial gate over article bodies")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--published", action="store_true", help="scan published articles")
    g.add_argument("--drafts", action="store_true", help="scan drafts")
    g.add_argument("--all", action="store_true", help="scan every article")
    g.add_argument("--slug", help="scan one article by slug or id")
    ap.add_argument("--quiet", action="store_true", help="counts only")
    args = ap.parse_args()

    sys.path.insert(0, "/home/fields/Fields_Orchestrator")
    from shared.db import get_client  # noqa: E402

    coll = get_client()["system_monitor"]["content_articles"]

    if args.slug:
        query = {"$or": [{"slug": args.slug}, {"_id": args.slug}]}
    elif args.published:
        query = {"status": "published"}
    elif args.drafts:
        query = {"status": {"$ne": "published"}}
    else:
        query = {}

    scanned = clean = acknowledged = 0
    breached: list[tuple[str, list[str]]] = []
    for doc in coll.find(query, {"slug": 1, "title": 1, "status": 1, "html": 1,
                                 "body": 1, "markdown": 1, "content": 1}):
        scanned += 1
        key = doc.get("slug") or str(doc.get("_id"))
        b = [x for x in check_article(doc) if not _is_acknowledged(key, x)]
        acknowledged += len(check_article(doc)) - len(b)
        if b:
            breached.append((f"{doc.get('slug')} [{doc.get('status')}]", b))
        else:
            clean += 1

    for name, b in breached:
        print(f"\n#### {name} — {len(b)} breach(es)")
        if not args.quiet:
            for item in b:
                print(f"   - {item}")

    print(f"\n== scanned {scanned} · clean {clean} · with breaches {len(breached)} · acknowledged-FP suppressed {acknowledged}")
    return 1 if breached else 0


if __name__ == "__main__":
    sys.exit(main())
