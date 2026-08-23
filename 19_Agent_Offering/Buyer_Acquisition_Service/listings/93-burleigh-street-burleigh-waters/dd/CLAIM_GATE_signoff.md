# 93 Burleigh — claim_gate sign-off (2026-08-23)

Ran `claim_gate.py --id 690bd81b8b8f546592617fbb --file <ad+infopack claims>`.
Result: 7 PASS · 2 NEEDS-QUALIFIER · 1 FAIL. Resolution below (human sign-off, per the gate's own
"a human confirms before publish" requirement).

**Fixed:** "$2.1M" → "$2,100,000" in the info pack + listing README (Rule 5 number format). Verified.

**FAIL — "The price guide is $1,915,000":** the gate flags any lone $ figure as a valuation-as-worth.
This is the **vendor's asking price**, a permitted fact ("a listing price is a fact"), and is labelled
"price guide"/"guide" everywhere it appears — not stated as Fields' valuation. **Overridden as a list
price, not a valuation.**

**NEEDS-QUALIFIER — comps range + "below the ~$2,100,000 cluster":** the $-claim pre-flight requires the
claim to land on a page that visibly shows methodology + a "not a valuation" disclaimer. **Satisfied:**
the info pack shows the comparable table + source ("compiled from public sale records") + "the price
guide is the current asking price, not a valuation"; the landing page shows the same. Comparable RANGES
are explicitly allowed.

**Net:** buyer-facing claims are cleared for publish **once** (a) Tyler clears the assets (conjunction
rule) and (b) the ad account is writable again (see below). No single Fields valuation figure is stated
as worth anywhere.
