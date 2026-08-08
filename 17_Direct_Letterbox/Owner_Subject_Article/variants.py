#!/usr/bin/env python3
"""
variants.py -- alternative compositions of the owner-subject article.

Why more than one
-----------------
The original composition is a REPORT: every heading is answered by the paragraph
under it, and the standfirst states the finding before the reader has formed a
question. It is thorough and it is flat.

These variants apply Loewenstein's information-gap idea -- awareness of a gap
between what you know and what you want to know produces the tension that drives
you to close it. Three conditions have to hold for a gap to be strong rather than
irritating:

  1. SELF-RELEVANT   it is about their home, not a category
  2. UNRESOLVABLE    they cannot close it by thinking harder or googling
  3. CREDIBLY CLOSED  they must believe we hold the missing piece --
                     which is why the named, dated evidence comes BEFORE the
                     biggest question in every variant here. A gap opened before
                     credibility is established reads as a tease.

⚠ THE RULE THAT SEPARATES THIS FROM MANIPULATION: every gap opened must be closed
IN THE SAME PIECE, with real evidence. We are not withholding to drive an action --
there is no action to drive; the piece has no CTA. In particular we do NOT defer a
gap to a later mailing. Holding back information about someone's own home to make
them wait is leverage over something that matters to them, and this reader has been
burned by confident people twice in eighteen months. `guardrails.TEASE` blocks the
constructions that do it.

Also note we are mostly not MANUFACTURING gaps. The reader already carries one --
"the number in my head might not be real" is ranked fear #3 in the homeowner brief.
Most of what follows makes an existing gap felt, then closes it.
"""
from __future__ import annotations


class Sections:
    """Shared, already-minted section builders. Variants choose order and framing."""

    def __init__(self, bundle, fb, charts, helpers):
        self.b, self.fb, self.charts = bundle, fb, charts
        self.fmt_date = helpers["fmt_date"]
        self.parse_date = helpers["parse_date"]
        self._upper1 = helpers["upper1"]
        self.charts_mod = helpers["charts_mod"]
        self.MAE_PCT = helpers["MAE_PCT"]

        b, fb = bundle, fb
        comps = b["comps"]
        self.comps = comps
        self.short = fb.address("subject_addr", b["address_short"])
        self.n_comps = fb.word_count("n_comps", len(comps))
        self.radius = fb.num("radius_km", b["radius_km"], dp=1)

        self.nearest = min(comps, key=lambda c: c["distance_km"])
        self.furthest = max(comps, key=lambda c: c["distance_km"])
        self.d_near = fb.num("d_nearest", self.nearest["distance_km"], dp=2)
        self.d_far = fb.num("d_furthest", self.furthest["distance_km"], dp=2)

        dates = sorted(d for d in (self.parse_date(c.get("sale_date")) for c in comps) if d)
        self.first_sale = fb.date("first_sale", self.fmt_date(dates[0]))
        self.last_sale = fb.date("last_sale", self.fmt_date(dates[-1]))

        adj = [c["adjusted_price"] for c in comps]
        raw = [c["sale_price"] for c in comps]
        self.adj_lo_v, self.adj_hi_v = min(adj), max(adj)
        self.raw_lo_v, self.raw_hi_v = min(raw), max(raw)
        self.adj_low = fb.money("adj_low", self.adj_lo_v)
        self.adj_high = fb.money("adj_high", self.adj_hi_v)
        self.raw_low = fb.money("raw_low", self.raw_lo_v)
        self.raw_high = fb.money("raw_high", self.raw_hi_v)
        self.adj_spread = fb.money("adj_spread", self.adj_hi_v - self.adj_lo_v)
        self.raw_spread = fb.money("raw_spread", self.raw_hi_v - self.raw_lo_v)

        # The two extremes by RAW price -- the anomaly the reader can see for
        # themselves before we explain anything.
        self.cheap = min(comps, key=lambda c: c["sale_price"])
        self.dear = max(comps, key=lambda c: c["sale_price"])
        self.narrowing_pct = (
            (1 - (self.adj_hi_v - self.adj_lo_v) / (self.raw_hi_v - self.raw_lo_v)) * 100
            if self.raw_hi_v > self.raw_lo_v else 0.0)

    # ---------------- shared blocks ----------------

    def macro(self, heading="What the headlines say"):
        b, fb = self.b, self.fb
        if not b["macro"]:
            return []
        bits = [fb.allow_literal(f"{s['text']} ({s['source']}, {s['period']})")
                for s in b["macro"]["stats"]]
        return [f"## {heading}\n",
                "The falls are real where they are being measured. "
                + " ".join(x + "." for x in bits)
                + " That is a fair picture of a national market under pressure.\n"]

    def comps_table(self):
        fb = self.fb
        out = ["| Address | Distance | Sold | Sale price | Adjusted for your home |",
               "|---|---|---|---|---|"]
        for i, c in enumerate(self.comps):
            out.append(
                f"| {fb.address(f'ca{i}', c['address'].split(',')[0])} "
                f"| {fb.num(f'd{i}', c['distance_km'], dp=2)} km "
                f"| {fb.date(f'sd{i}', self.fmt_date(c.get('sale_date')))} "
                f"| {fb.money(f'sp{i}', c['sale_price'])} "
                f"| {fb.money(f'ap{i}', c['adjusted_price'])} |")
        out.append("")
        return out

    def what_sold_intro(self):
        fb = self.fb
        return [
            f"{self.n_comps.capitalize()} houses have sold close to yours between "
            f"{self.first_sale} and {self.last_sale}. The nearest is "
            f"{fb.address('nearest_addr', self.nearest['address'].split(',')[0])}, "
            f"{self.d_near} km away; the furthest in this set is {self.d_far} km. They "
            f"are the evidence here, because a sale down the road is a real transaction, "
            f"not an estimate.\n"]

    def worked_example(self, lead=None):
        """The adjustment mechanism, shown on one real sale."""
        fb, we = self.fb, self.b["worked"]
        if not we:
            return []
        c = we["comp"]
        c_addr = fb.address("we_addr", c["address"].split(",")[0])
        c_price = fb.money("we_price", c["sale_price"])
        c_adj = fb.money("we_adj", c["adjusted_price"])
        c_date = fb.date("we_date", self.fmt_date(c.get("sale_date")))
        clauses = []
        for i, m in enumerate(we["moves"]):
            verb = "we add" if m["dollars"] > 0 else "we subtract"
            amt = fb.money(f"we_move_{i}", abs(m["dollars"]))
            if m["unit"] == "sqm" and m["subject"] is not None and m["comp"] is not None:
                sv = fb.num(f"we_subj_{i}", m["subject"])
                cv = fb.num(f"we_comp_{i}", m["comp"])
                clauses.append(f"it has {cv} sqm of {m['label']} against your {sv}, "
                               f"so {verb} {amt}")
            else:
                clauses.append(f"on {m['label']}, {verb} {amt}")
        tail = (f", with {fb.word_count('we_other', we['n_other'])} smaller differences"
                if we["n_other"] else "")
        lead = lead or ("A raw sale price is not directly comparable to your home, though, "
                        "because no two houses are the same.")
        return [f"{lead} Take {c_addr}, which sold on {c_date} for **{c_price}** -- a real "
                f"sale price. " + self._upper1("; ".join(clauses)) + f"{tail}. Those "
                f"differences restate that sale as **{c_adj}** -- an estimate of what that "
                f"same buyer would likely have paid for a home like yours.\n"]

    def range_para(self, heading="What these sales say about your home"):
        return [f"## {heading}\n",
                f"Raw, those {self.n_comps} homes sold between {self.raw_low} and "
                f"{self.raw_high}. Adjusted to your home, they land between "
                f"**{self.adj_low} and {self.adj_high}** -- a range built from "
                f"{self.n_comps} sales. That spread of {self.adj_spread} is the estimate. "
                f"It is not one number, and it should not be read as one; the width is the "
                f"honest part, reflecting how the {self.n_comps} homes genuinely differed "
                f"from yours.\n"]

    def dom_section(self, heading=None, opener=None):
        b, fb = self.b, self.fb
        dom = b.get("dom")
        if not dom or not dom.get("timeline"):
            return []
        svg, cap = self.charts_mod.dom_chart(dom["timeline"], b["suburb_display"], fb)
        if not svg:
            return []
        self.charts["dom"] = svg
        latest = fb.num("dom_latest", dom["latest"])
        heading = heading or f"How long homes are taking to sell in {b['suburb_display']}"
        opener = opener or (
            f"Half the houses that sold in {b['suburb_display']} last quarter were under "
            f"offer within {latest} days of listing, and half took longer. The chart below "
            f"shows that figure each quarter, with the number of sales it is measured from "
            f"underneath.")
        return [f"## {heading}\n", opener + "\n", "{{CHART:dom}}", f"*{cap}*\n"]

    def median_chart(self):
        b, fb, sm = self.b, self.fb, self.b["suburb"]
        if not sm or not sm.get("series"):
            return []
        svg, cap = self.charts_mod.median_price_chart(
            sm["series"], b["suburb_display"], fb)
        if not svg:
            return []
        self.charts["median"] = svg
        return ["{{CHART:median}}", f"*{cap}*\n"]

    def suburb_agreement(self, heading=None):
        """The comps' own movement against the suburb's recorded median."""
        b, fb = self.b, self.fb
        mv, sm = b["movement"], b["suburb"]
        if not (mv and sm):
            return []
        head = heading or f"Do these sales agree with {b['suburb_display']}'s own figures?"
        out = [f"## {head}\n"]
        e_mean = fb.money("early_mean", mv["early_mean"])
        l_mean = fb.money("late_mean", mv["late_mean"])
        n_e = fb.word_count("n_early", mv["n_early"])
        n_l = fb.word_count("n_late", mv["n_late"])
        move = fb.pct("comp_move", mv["pct"])
        yoy = fb.pct("suburb_yoy", sm["yoy_pct"])
        window = fb.num("median_window_months", 12)
        n_sales = fb.num("n_suburb_sales", sm["n_now"])
        out.append(
            f"Split the {self.n_comps} adjusted sales in half by date. The earlier {n_e}, "
            f"from {fb.date('e_from', self.fmt_date(mv['early_from']))} to "
            f"{fb.date('e_to', self.fmt_date(mv['early_to']))}, average **{e_mean}**. The "
            f"later {n_l}, from {fb.date('l_from', self.fmt_date(mv['late_from']))} to "
            f"{fb.date('l_to', self.fmt_date(mv['late_to']))}, average **{l_mean}**. That "
            f"is a move of **{move}**.\n")
        same_dir = (mv["pct"] > 0) == (sm["yoy_pct"] > 0)
        close = same_dir and abs(mv["pct"] - sm["yoy_pct"]) <= 2.5
        lead = (f"The {b['suburb_display']} rolling {window}-month house median moved "
                f"**{yoy}** year-on-year, across {n_sales} sales matched between Domain "
                f"and onthehouse. ")
        if close:
            verdict = "Both point the same way, and by a similar amount."
        elif same_dir:
            bigger = ("these sales" if abs(mv["pct"]) > abs(sm["yoy_pct"])
                      else "the suburb median")
            verdict = (f"Both point the same way, though not by the same amount -- "
                       f"{bigger} moved further.")
        else:
            verdict = (f"These two records point in opposite directions, which is a fact "
                       f"about how little {self.n_comps} sales can settle rather than a "
                       f"contradiction to resolve.")
        out.append(lead + verdict + "\n")
        out += self.median_chart()
        mae = fb.pct("mae", self.MAE_PCT, signed=False)
        halves = n_e if mv["n_early"] == mv["n_late"] else f"{n_e} and {n_l}"
        closing = ("The direction is the reportable part; the precision either figure "
                   f"appears to show is more than {n_e} sales a side can carry."
                   if close else
                   "Neither figure is precise enough to explain the difference between "
                   "them, so the honest reading is the direction they share, not the gap.")
        out.append(
            f"Now the limits, in the same breath. Each half holds {halves} sales, which is "
            f"a very small sample. This method's own mean absolute error is about {mae} in "
            f"this price range -- wider than the movement it is describing. " + closing + "\n")
        return out

    def limits(self, heading="What this can't tell you"):
        b, fb, sm = self.b, self.fb, self.b["suburb"]
        mae2 = fb.pct("mae2", self.MAE_PCT, signed=False)
        t = (f"We publish this method's mean absolute error: about {mae2} in this price "
             f"range. {self.n_comps.capitalize()} sales sit behind the range above -- a "
             f"small number, stated plainly so you can weigh it. ")
        if sm:
            t += (f"The {b['suburb_display']} median rests on "
                  f"{fb.num('n_suburb_sales2', sm['n_now'])} recorded sales, which is a "
                  f"sample of the suburb's activity rather than all of it. ")
            if sm.get("ci_low") and sm.get("ci_high"):
                t += (f"Its {fb.pct('sub_ci_level', 90, signed=False, dp=0)} confidence "
                      f"range runs {fb.money('sub_ci_low', sm['ci_low'])} to "
                      f"{fb.money('sub_ci_high', sm['ci_high'])}. ")
        t += (f"Sales within {self.radius} km of one home, over "
              f"{fb.num('span_months', b['span_months'])} months, cannot show you a whole "
              f"market or what any single buyer would do.\n")
        return [f"## {heading}\n", t]

    def radius_note(self, MIN_COMPS, RADIUS_KM):
        fb = self.fb
        if not self.b["radius_widened"]:
            return []
        return [f"*Fewer than {fb.word_count('min_comps', MIN_COMPS)} comparable sales fell "
                f"inside the standard {fb.num('std_radius', RADIUS_KM, dp=1)} km, so the "
                f"search was widened to {self.radius} km for this home.*\n"]


# ------------------------------------------------------------------ variants

def v_anomaly(S, MIN_COMPS, RADIUS_KM):
    """GAP: two homes near you, both like yours, sold far apart. Why?

    Our strongest prediction error. The reader can verify the raw prices, and their
    model says these are different markets. Adjustment is the resolution -- and
    where it only partly resolves, the copy says so rather than overclaiming.
    """
    fb, b = S.fb, S.b
    cheap = fb.address("an_cheap", S.cheap["address"].split(",")[0])
    dear = fb.address("an_dear", S.dear["address"].split(",")[0])
    cheap_p = fb.money("an_cheap_p", S.cheap["sale_price"])
    dear_p = fb.money("an_dear_p", S.dear["sale_price"])
    cheap_a = fb.money("an_cheap_a", S.cheap["adjusted_price"])
    dear_a = fb.money("an_dear_a", S.dear["adjusted_price"])
    gap_raw = fb.money("an_gap_raw", S.dear["sale_price"] - S.cheap["sale_price"])
    gap_adj = fb.money("an_gap_adj",
                       abs(S.dear["adjusted_price"] - S.cheap["adjusted_price"]))

    # ⚠ No money figure in the headline -- a bright line, held even though this one is a
    # DIFFERENCE between two other homes' sale prices rather than a valuation of the
    # reader's. The gap survives one sentence of delay; the rule is worth more than the
    # headline. The figures land immediately below, where they have context.
    P = [f"# Two sales near you point to very different numbers for your home\n"]
    P.append(
        f"{dear} sold for {dear_p}. {cheap} sold for {cheap_p} — {gap_raw} between them. "
        f"Both are within {S.d_far} km of {S.short}, both are houses, both sold in the "
        f"same stretch of months. On the face of it they describe two different markets. "
        f"They do not, and the reason is the whole of what follows.\n")

    P.append("## The sales themselves\n")
    P += S.what_sold_intro()
    P += S.worked_example(
        lead="A sale price answers a question about that house, not about yours. Before "
             "two sales can be compared, each has to be restated as what it implies for "
             "the home you are standing in.")
    P += S.comps_table()

    P.append("## What happened to the gap\n")
    close = abs(S.dear["adjusted_price"] - S.cheap["adjusted_price"])
    if close < (S.dear["sale_price"] - S.cheap["sale_price"]) * 0.6:
        P.append(
            f"Once each is adjusted to your home, {dear} reads as {dear_a} and {cheap} as "
            f"{cheap_a} -- {gap_adj} apart instead of {gap_raw}. Two sales that looked "
            f"like different markets were largely describing the same one. The difference "
            f"was mostly the houses, not the market.\n")
    else:
        P.append(
            f"Once each is adjusted to your home, {dear} reads as {dear_a} and {cheap} as "
            f"{cheap_a} -- {gap_adj} apart, against {gap_raw} raw. Adjusting explains part "
            f"of the distance between them and not all of it. On this pair the houses "
            f"account for less of the gap than they often do, which is worth knowing "
            f"before leaning on either sale.\n")
    # ⚠ Those two are the EXTREMES of the set, so their collapse is the most dramatic in
    # it. Left alone that overstates the method -- the standing rule is never to quote the
    # best pair as typical. So the whole-set figure goes in the same breath.
    set_raw = fb.money("an_set_raw", S.raw_hi_v - S.raw_lo_v)
    set_adj = fb.money("an_set_adj", S.adj_hi_v - S.adj_lo_v)
    P.append(
        f"That pair is the widest in the set, so it is also where adjusting does the most "
        f"visible work. Across all {S.n_comps} sales the effect is smaller: {set_raw} "
        f"between the cheapest and dearest raw price, {set_adj} once each is adjusted.\n")
    P += S.range_para("Where that leaves your home")
    P += S.dom_section()
    P += S.suburb_agreement()
    P += S.macro("What the national numbers are saying meanwhile")
    P += S.limits()
    P += S.radius_note(MIN_COMPS, RADIUS_KM)
    return P


def v_anchor(S, MIN_COMPS, RADIUS_KM):
    """GAP: you are carrying a number for this house. Where did it come from?

    Ranked fear #3 -- "the number in my head might not be real". The gap already
    exists in the reader; this names it. Careful framing: we never say their number
    is wrong, because we do not know it. We show what the evidence supports and let
    them do the comparison.
    """
    fb, b = S.fb, S.b
    P = [f"# You already have a number for {S.short}\n"]
    P.append(
        "Most owners do. It came from somewhere — a sale down the street, an online "
        "estimate, a figure a neighbour mentioned, or the market as it was two years ago. "
        "What almost nobody has is the working behind it. This is the working for your "
        "address, from sales you can look up yourself.\n")

    P.append("## The sales it rests on\n")
    P += S.what_sold_intro()
    P += S.comps_table()
    P += S.worked_example(
        lead="Those are real prices for other houses. Turning them into anything about "
             "yours means accounting for how each one differs from it.")
    P += S.range_para("What the working produces")
    P.append(
        "If the number you were carrying sits inside that range, the evidence near you "
        "supports it. If it sits outside, that is worth knowing now rather than at the "
        "point where it matters. We are not in a position to tell you which, because we "
        "do not know your number — only what these sales, adjusted, come to.\n")
    P += S.dom_section()
    P += S.suburb_agreement()
    P += S.macro("Why the national headlines may not match it")
    P += S.limits()
    P += S.radius_note(MIN_COMPS, RADIUS_KM)
    return P


def v_features(S, MIN_COMPS, RADIUS_KM):
    """GAP: which of YOUR features are moving the number, and by how much?

    The most self-relevant of the set. The worked example already decomposes a
    comparable; this variant makes the decomposition the spine, because a reader
    who sees land and condition priced on someone else's house immediately wants
    the same arithmetic on their own.
    """
    fb, b, we = S.fb, S.b, S.b["worked"]
    P = [f"# What your land, your condition and your floor area are worth in {b['suburb_display']}\n"]
    P.append(
        f"Not as an opinion. Every sale near you can be restated as what that same buyer "
        f"would likely have paid for a home like yours, and doing that puts a figure on "
        f"each difference — land, floor area, condition, what is in the kitchen. Those "
        f"figures are below, on {S.n_comps} real sales within {S.radius} km of {S.short}.\n")

    P.append("## The arithmetic, on one sale\n")
    P += S.worked_example(
        lead="Here is the method with nothing hidden, applied to the sale nearest to "
             "yours in character.")
    if we and we["moves"]:
        biggest = we["moves"][0]
        amt = fb.money("ft_biggest", abs(biggest["dollars"]))
        P.append(
            f"The single largest correction there is {amt}, on {biggest['label']}. That is "
            f"the scale at which one feature moves a comparison — which is why two houses "
            f"on the same street can be poor guides to one another.\n")
    P.append("## The same arithmetic on every sale near you\n")
    P += S.what_sold_intro()
    P += S.comps_table()
    P += S.range_para("What they come to, together")
    P += S.dom_section()
    P += S.suburb_agreement()
    P += S.macro("The national picture, for context")
    P += S.limits()
    P += S.radius_note(MIN_COMPS, RADIUS_KM)
    return P


def v_timing(S, MIN_COMPS, RADIUS_KM):
    """GAP: homes here are selling in about N days -- which half would yours be in?

    Leads with time-on-market per the homeowner brief §8.3 (more reliable in our
    data than medians, and structurally non-advisory). Answers the owner's first
    question -- will it sell at all -- before the question of price.
    """
    fb, b = S.fb, S.b
    dom = b.get("dom")
    P = []
    if dom:
        latest = fb.num("dom_latest_hd", dom["latest"])
        P.append(f"# Half the houses in {b['suburb_display']} sold within {latest} days. "
                 f"The other half did not\n")
        # No causal claim about WHY a home lands on one side -- we have not measured that,
        # and asserting it would be an opinion wearing a fact's clothes.
        P.append(
            "Which side a home lands on is the question an owner actually wants answered, "
            "and a suburb median cannot answer it. What follows is narrower and more "
            "useful: the sales a buyer would have been weighing against yours, in the "
            "same weeks, and what each of them implies for this address.\n")
    else:
        P.append(f"# What recent sales near {S.short} actually did\n")
        P.append("The sales below are the evidence, because each one is a real "
                 "transaction rather than an estimate.\n")
    P += S.dom_section(heading="How long it has been taking")
    P.append("## The homes yours would have been compared with\n")
    P += S.what_sold_intro()
    P += S.worked_example(
        lead="A buyer choosing between them is not comparing sticker prices, and neither "
             "can we — each sale has to be restated in terms of your home.")
    P += S.comps_table()
    P += S.range_para("What that puts on your home")
    P += S.suburb_agreement()
    P += S.macro("Set against the national headlines")
    P += S.limits()
    P += S.radius_note(MIN_COMPS, RADIUS_KM)
    return P


def v_contradiction(S, MIN_COMPS, RADIUS_KM):
    """GAP: the national numbers and your street disagree. Which one is your home in?

    The current article's framing, but with the resolution withheld from the
    standfirst so the tension survives to the evidence. Closest to the homeowner
    brief §8.1 -- name the ambiguity before resolving anything.
    """
    fb, b = S.fb, S.b
    P = [f"# The national numbers and your street are not describing the same market\n"]
    P.append(
        f"One of them is measured across five capital cities. The other is "
        f"{S.n_comps} houses within {S.radius} km of {S.short}. They currently point "
        f"different ways, and no amount of reading either one resolves the other. Both "
        f"are below, with what each can and cannot tell you about this address.\n")
    P += S.macro("What the national numbers say")
    P.append("## What your street says\n")
    P += S.what_sold_intro()
    P += S.worked_example()
    P += S.comps_table()
    P += S.range_para()
    P += S.dom_section()
    P += S.suburb_agreement()
    P += S.limits("Which leaves what unresolved")
    P += S.radius_note(MIN_COMPS, RADIUS_KM)
    return P


VARIANTS = {
    "anomaly": (v_anomaly, "Two sales that look like different markets (prediction error)"),
    "anchor": (v_anchor, "The number already in your head (fear #3)"),
    "features": (v_features, "What your own features are worth (most self-relevant)"),
    "timing": (v_timing, "Will it sell, and which half (days-on-market led)"),
    "contradiction": (v_contradiction, "National vs your street, left unresolved"),
}
