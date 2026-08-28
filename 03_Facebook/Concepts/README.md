# Facebook Ad Concepts

One folder per concept. A concept starts as a `README.md` brief (the idea, the flow, the
data it needs, the compliance flags) and graduates to build files (reel scene, render
script, landing page, launch script) as it moves toward test.

| Concept | Folder | Format | Status |
|---------|--------|--------|--------|
| Selling-month guessing game — "Worst month to sell in Robina" | [`Selling_Month_Guessing_Game/`](Selling_Month_Guessing_Game/) | Interactive Reel → replicated landing page → 2-round quiz → address capture | Brief |
| "The best house isn't even on the market" — off-market buyer matching | [`Off_Market_Match_Finder/`](Off_Market_Match_Finder/) | Reel/static → 2-step form (brief + contact) | Brief |

## House pattern for a concept

- **The ad *is* the product.** Where a concept opens a landing page from a reel, the landing
  page replicates the reel's final frame so the hand-off has no visible cut. See
  `../Price_Your_Own_Home/` for the reference build (deterministic `window.seek(ms)` scene →
  Puppeteer frame capture → mp4).
- **Editorial rules are not optional** (CLAUDE.md §5). Data only, no advice, no single
  valuation in a headline, comparable **ranges** not single figures. Any $ claim in an ad must
  point to a landing page that shows methodology + a confidence disclaimer.
- **Every $ figure must trace to real Robina data before it goes live.** Placeholder numbers in
  a brief are flagged as such.
