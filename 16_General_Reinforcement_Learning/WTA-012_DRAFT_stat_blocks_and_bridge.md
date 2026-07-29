# WTA-012 — DRAFT for review (not deployed)

**Two changes to the market-metrics pages, drafted for Will's approval.** Both come from GEO cycle #1:
AI-chat engines (Copilot/ChatGPT) land ~100% on `/market-metrics/Gold-Coast/overview` and stop — the page is
data-rich but (a) not in the format LLMs extract-and-cite, and (b) has no visible bridge to "what's MY home worth".

**Editorial compliance (CLAUDE.md Rule 5):** market **medians/aggregates** are fine (not single-property
valuations); every stat cites source + period; no advice, no predictions; ranges where a figure is a property
value. **Data binds to the page's existing source — never hardcoded** (the `CrashRiskSection` stale-data lesson).

**Performance (Will's hard constraint):** both additions are **static SSR content already in the payload** — no
new fetch, no client JS, no added latency. The stat blocks render from data the page already loads; the bridge is
a plain `<a>`. Zero LCP impact.

---

## Change 1 — "At a Glance" quotable stat blocks

**Where:** top of `MarketMetricsPage` overview, above the charts. **Data:** bind to the same market object the
page already renders (median, DOM, volume, growth) — shown here as `data.*` placeholders; wire to the real fields.

```tsx
// StatSnapshot.tsx — question-H2 + extractable stat + source. LLMs cite this shape.
<section className={styles.snapshot} aria-label="Market at a glance">
  <StatBlock
    q="What is the median house price on the Gold Coast?"
    a={<>The median house price across Robina, Varsity Lakes and Burleigh Waters is{" "}
       <strong>{fmtAUD(data.medianPrice)}</strong> ({data.period}), based on {data.txnCount} verified sales.</>}
    source={`Fields Estate analysis of ${data.txnCount} verified sales, ${data.period}.`} />
  <StatBlock
    q="How long do Gold Coast houses take to sell?"
    a={<>Median days on market is <strong>{data.medianDom} days</strong> ({data.period}){" "}
       {data.domPrevQ != null && <>versus {data.domPrevQ} in {data.prevPeriod}</>}.</>}
    source={`Fields Estate transaction tracking, ${data.period}.`} />
  <StatBlock
    q="Is the Gold Coast market growing?"
    a={<>Median values across the tracked suburbs moved <strong>{fmtPct(data.growthYoY)}</strong> year-on-year{" "}
       ({data.period}). Individual suburbs vary — see the breakdown below.</>}
    source={`Fields Estate analysis, ${data.period}.`} />
</section>
```

- **Why:** Princeton GEO study — pages with statistics + citations get 30–40% higher AI visibility; each block is a
  standalone extractable unit (question → stat → source), which LLMs prefer over synthesis-across-charts.
- **Also add FAQPage JSON-LD** mirroring these Q→A pairs (the page already has FAQ schema; extend it to match).
- **Guard:** the stat values must come from the live market object; if a field is missing, the block hides (no
  "$undefined"). Never commit numbers into the JSX.

## Change 2 — market-metrics → AYH bridge

**Where:** after the snapshot (and/or end of overview). A single soft, editorial-compliant link — the "what's MY
number" mechanic that both Bing conversions used.

```tsx
<aside className={styles.bridge}>
  <p>These are suburb-wide figures. <a href="/analyse-your-home">See how your home compares →</a></p>
</aside>
```

- **Copy is data-framed, no advice/CTA-pressure** (soft CTA per feedback_cta_strategy). Alternatives for A/B later:
  "See the comparable-sales range for your address →" / "What do these numbers mean for your street? →".
- **Why:** 41% of Bing + 100% of Copilot/ChatGPT sessions start on market-metrics and never reach AYH because
  there's no visible next step. Even 1-in-10 bridging adds ~0.3 seller conversions/mo from the AI channel at $0.

## Also ready (no WTA needed — safe static file, like robots.txt): llms.txt
A `/llms.txt` listing our key citable pages (market-metrics, methodology, research) — the emerging convention for
LLM discovery. Additive, static, zero-risk. Can ship with the above or standalone. Flagged as ACTION 6 in the cycle.

---

**Ask:** approve Change 1 + Change 2 (and llms.txt?) for implementation. On approval I'll wire to the real data
fields, verify editorial + build, and deploy in one commit with visual verification.
