# The Fields Quarterly — Q2 2026 handoff

**Written:** 2026-08-01, ~21:00 AEST, at the end of a long working session with Will.
**For:** a Claude Code session picking this up cold.
**Task:** write the Q2 2026 report. The data work underneath it is done; the writing is not.

Read this whole file before touching anything. Most of the traps below cost hours to rediscover,
and three of them produced wrong numbers on the live website today.

---

## 1. What this project is

The Fields Quarterly is a printed + digital property market report for the southern Gold Coast
(Robina, Burleigh Waters, Varsity Lakes). Fields is **pre-revenue, sole operator (Will Simpson), no
clients, no sales track record.** Its entire market position is *original analysis published with
its method exposed* — "smarter with data".

That constraint shapes every editorial decision: we cannot win on testimonials or track record
because we have none. We win on being demonstrably, checkably right.

## 2. THE ONE ARCHITECTURAL RULE

> **`https://fieldsestate.com.au/market-intelligence/` is the single source of truth. The report
> READS from it. The report NEVER computes its own numbers.**

Will stated this explicitly this session. Every divergence we found today traced back to the report
computing its own figures instead of reading the site's — including an absorption rate that made
Robina look like a balanced market on paper and a seller's market on the website.

If the report and the site ever disagree, **the site is right and the report is wrong.** That is now
an architectural property, not a discipline: `scripts/precompute_union_prices.py` writes the site's
numbers, and the report must quote them.

---

## 3. VERIFIED DATA — as at 2026-08-01, live on the site

| Suburb | 12-month median | 90% CI | n | YoY |
|---|---|---|---|---|
| **Burleigh Waters** | **$1,925,000** | $1,855,550–$2,000,000 (±3.9%) | 167 | +6.9% |
| **Robina** | **$1,490,000** | $1,450,000–$1,550,000 (±4.0%) | 265 | +5.8% |
| **Varsity Lakes** | **$1,400,000** | $1,380,000–$1,450,000 (±3.6%) | 111 | +10.2% |

**External validation:** realestate.com.au publishes Burleigh Waters at **$1,910,000 on 195 sales**,
same methodology, same window. We are within **0.8%** on the median; our 167 priced + ~32
price-withheld ≈ 199 against their 195. This cross-check is the single most valuable credibility
asset in the issue — consider printing it.

**Volume (union basis, complete quarters only):**

| Suburb | Q4 2025 | Q1 2026 | Q2 2026 |
|---|---|---|---|
| Burleigh Waters | 41 | 44 | **42 (flat)** |
| Robina | 71 | 71 | **51** |
| Varsity Lakes | 45 | 31 | **17** |

Q3 2026 (12 / 8 / 7) is **in progress — never chart it as complete.** Q2 2026 is still filling in as
settlements register, so all three are floors.

**Quarterly medians — check `reliable` before quoting:** Burleigh Waters Q2 `$1,877,775 ±8.7%
reliable=False` · Robina `$1,410,000 ±9.9% reliable=False` · Varsity Lakes `$1,410,000 ±6.4%
reliable=True` **but on n=17** — the flag gates on CI width only, not sample size, so treat it as
unreliable too.

Full detail: `working_notes/03_q2_2026_evidence_pack.md`.

---

## 4. WHAT WE MAY NOT SAY — and why

These are not style preferences. Each one was published, was wrong, and was corrected today.

| Forbidden claim | Why |
|---|---|
| **"Double-digit growth"** across the region | Only Varsity Lakes reaches double digits. The old 10.9/12.2/15.5% figures were PropRadar's `growth_1y_pct` and are gone. |
| **"Sales halved" / "volume collapsed"** | We published Robina −67% and Burleigh Waters −30%. On a fuller transaction set Burleigh Waters is **flat**. The old figures were an artefact of a source whose capture decays for recent quarters. |
| **Any quarter-on-quarter median move** | Q2 CIs run ±6.4% to ±9.9%. Nothing this quarter clears the noise. |
| **Year-on-year volume comparison** | onthehouse only reaches back to August 2025; a YoY figure would compare a union quarter against a Domain-only one. |
| **"Burleigh Waters is accelerating"** | Published in the Q2 issue. It rested on an uncalibrated series and was an artefact. |
| **Absorption-led "seller's market"** without caveat | Absorption comes from PropRadar's `house_inventory_months`, built on counts we demoted for the median (240 BW houses vs REA's 195). Inflated sales in the denominator make stock look like it clears faster, so absorption is probably **understated**. |
| **Any long-run volume chart** | Pre-Q4 2025 volume is Domain-only, undercounts 25–55%, and crosses two composition shifts (sold-listing feed arriving ~Q4 2024; property timelines going stale ~Q4 2025). |

Plus the standing CLAUDE.md rules: **no advice, no forecasts, no single valuation in a headline,
exact prices, no forbidden words** ("stunning", "nestled", "boasting", "rare opportunity", "robust
market").

---

## 5. DO NOT COPY FROM THESE — they are stale or wrong

| File | Problem |
|---|---|
| `issues/q2_2026/latest.pdf` (published 24 Jul) | Wrong medians, wrong volume direction, claims Burleigh Waters is accelerating, leads with the Conviction Index. Useful only as a "what not to do" reference. |
| `drafts/q2_2026_editorial_outline.md` (28 Jul) | Read the site correctly at the time, but every figure has since moved. Its national-vs-local spine is still arguable; its numbers are not. |
| `issues/q2_2026_quarterly/latest.pdf` (36pp) | Superseded by the per-suburb decision. |
| `system_monitor.market_pulse` prose | Was regenerating when this was written. **Verify before quoting.** Prose/commentary is a separate session Will has explicitly deferred. |

---

## 6. FORMAT DECISIONS AND THE EVIDENCE BEHIND THEM

**Decision: one report per suburb.** Not one combined report covering three.

Evidence: Alex Jordan's report (`research/alex_jordan_report/`, 23 pages, PNG scans) — the agent Will
admires — did **one suburb per report** (Indooroopilly). Reading his actual pages was decisive and
surprising: cover is the suburb name only, no number; ~250 words of lifestyle-led commentary signed
by hand; **page 3 is about him** (headshot, mobile, email); page 14 is two charts of public
pricefinder data; **page 20 is a feature on a local bar**.

So roughly **three pages of data**; the bulk is **sold listings with named client testimonials plus
local lifestyle content**. His authority came from social proof and local embeddedness, **not
analytical depth** — and the length is filled with exactly the two things Fields does not have. A
36-page Fields report would have ~30 pages to fill and nothing to fill them with.

**Decision: eight pages.** Not a target — it is where content that genuinely earns a place runs out.

Evidence from Brain 1 (`research/brain1_printed_report_evidence.md`, quotes re-verified against
source units after a verifier bug was found — see §8):
- The corpus's only explicit page count is **eight** — a "beautiful glossy booklet", posted to 3,264
  contacts four times a year, each mailing paired with a phone call, claimed to produce 50% of sales.
- **Frequency outranks length:** *"better off doing 5,000 letter box drops a week to the same people
  each week than just doing one person once in a month"*.
- **The report's job is to earn the next contact, not to persuade.** It is a permission device.
- *"80% of sales are made from the fifth to the twelfth contact"*; printed material *"tapers off very
  quickly"* after ~14 days.
- **No direct readership measurement exists anywhere in the corpus.** Every "they read it" claim is
  assertion or inference.

**Decision: the Fields Conviction Index is dropped from the issue but still computed.** It is
unfalsifiable to a reader, needs a paragraph of explanation, and asks for trust before we have earned
it — in a category where agents rank third-least-trusted profession in Australia. Keep computing it:
the time series is a genuine asset and the continuity spine.

---

## 7. WHO THIS IS ACTUALLY FOR — the numbers that reframe everything

`lead_worklist`: **297 non-test leads.** 232 with a mailable address, **27 with email, 3 with
phone**, and **210 carrying "no strong intent signal yet"** — a single address lookup and nothing
since. The genuinely warm list is **~46 people**.

This is **not a database-nurture programme**. There is no database yet. The quarterly's real job is
**acquisition** — a public artefact good enough that people hand over an address, and rich enough to
cut into months of social content. The 20-page personalised appraisal (ops → Appraisals tab) is the
instrument for the warm few.

**Will's social campaign content arrives Tuesday 2026-08-05.** He has asked that the report be
designed knowing that — likely web-first and cuttable, every page able to stand alone as a social
post or YouTube segment. **Confirm with him before assuming.**

Related, scoped but not built: `17_Direct_Letterbox/00_SCOPING.md` — personalised card with the
recipient's own house photo (we hold **14,546 properties with photos** in
`/data/blobs/property-images/cadastral/`) and a per-address QR. That is the intended frequency rail
between quarterlies.

---

## 8. THE ISSUE SPEC — read it, then argue with it

`working_notes/04_q2_2026_issue_spec.md`. Burleigh Waters edition. Summary:

**Lead number: `42`** — *"Forty-two houses sold in Burleigh Waters last quarter. Forty-four the
quarter before. The market you're reading about isn't the one on your street."*

Chosen against criteria that should be reused every issue: the reader can verify it against their own
experience; it describes their position rather than our cleverness; it needs no definition; it moved
meaningfully. It also contradicts the national story the reader arrives with, which is the most
useful thing available this quarter.

**Eight pages, each with a stated job:** cover · what changed (signed, ~250 words) · the number and
how sure we are (with the REA cross-check) · activity not price · one sale in full · what it costs to
move · how to read a price estimate · what this can't tell you.

**Page 8 carries the continuity ledger** and must say plainly that **we published a 30% volume fall
last quarter and it was flat**. Admitting that in print costs nothing but nerve and is the strongest
trust move available.

**Two questions were open with Will when this was written:**
1. Does `42` work as a cover number, or is it too small to carry a cover?
2. Page 6 (what it costs to move) needs onward-purchase data we do not hold — what the next rung
   costs and servicing at 4.35%. Build it, or ship seven pages and add it in Q3?

---

## 9. STILL TO DO

1. **Source the page-5 case study** — a real Q2 2026 Burleigh Waters settlement from the union set.
   **Must clear the currently-listed guard** (PropRadar real-time check) — ~0.75% of homes are on the
   market at any time, and featuring one listed with another agent would be a serious own goal.
2. **Page 6 onward-purchase data** — or drop to seven pages.
3. **Write it.**
4. **Photography** — per the Alex Jordan finding, identity and place matter more than we assumed.
5. **Extract the reusable process** (`working_notes/02_problem_register.md` P3.1–P3.6): master
   quarterly cycle, sentiment-research brief, editorial council agenda, issue spec template, evidence
   pack template, continuity ledger. Will asked for this at the very start of the session and it is
   the durable deliverable.

---

## 10. TRAPS

**Data**
- `market-insights?suburb=Burleigh-Waters` **used to** silently return the Gold Coast aggregate. Fixed
  today, but `gold_coast_average` is **still on the old basis** and is served on any lookup miss.
- The volume **chart** and the insights **strip** read different collections. Both now prefer the
  union series, but `indexed_series[].transaction_count` is still the old calibrated value — it was
  deliberately left alone because `market-insights.mjs:677` does `salesVolume: q.transaction_count || 0`,
  so nulling it would render years of history as a flat line at zero.
- `precompute_indexed_price_data.py` does a **full `replace_one`** on the 1st of the month.
  `precompute_union_prices.py` runs at `40 5 1 * *` **after** it, deliberately, and is what keeps the
  corrected medians alive. **Do not reorder the cron.**

**Process**
- Rule 1: log every change to `logs/fix-history/YYYY-MM-DD.md`. Rule 2: push via `gh api` (git push
  hangs on this VM). Rule 7: any new scheduled process must wrap `job_run()`.
- **Batch website pushes into ONE commit** via the git trees API — separate `contents` PUTs burn a
  Netlify deploy each and can leave `published_at: null`.
- Bare `tsc` checks **zero** files. Use `npx tsc -p tsconfig.app.json --noEmit` plus `npm run build`.
  Note both passed a change that put a 14-sale part-quarter on the live page as "the median house
  price" — **only reading the rendered page caught it.**

**Judgement**
Three times today a conclusion was built on a broken measurement — an uncalibrated price series, a
verifier that summed 1-character matches, and a `pgrep` that matched itself and reported a finished
job as running. Each looked authoritative. **Before building on a number, test the instrument that
produced it against a case whose answer you already know.**

---

## 11. WHERE THINGS LIVE

```
10_Market_Report/
├── HANDOFF_Q2_2026.md                        ← this file
├── working_notes/02_problem_register.md      ← every defect found, with status
├── working_notes/03_q2_2026_evidence_pack.md ← verified numbers + what we may not say
├── working_notes/04_q2_2026_issue_spec.md    ← the issue plan
├── research/alex_jordan_report/              ← 23 PNG pages, read 02/14/20 first
├── research/brain1_printed_report_evidence.md
└── pipeline/quarterly/INTEGRATION.md         ← render pipeline

scripts/precompute_union_prices.py            ← writes the site's medians + CIs + union volume
shared/dwelling_type.py                       ← one definition of "house"
scripts/samantha/BRAIN_FIXES_HANDOFF.md       ← Brain 1/2/3 reliability work
17_Direct_Letterbox/00_SCOPING.md             ← the frequency rail
logs/fix-history/2026-08-01.md                ← ten entries from this session
```

**First command to run:** `python3 scripts/precompute_union_prices.py` (no `--promote`) — prints the
current numbers and confirms nothing has drifted since this was written.
