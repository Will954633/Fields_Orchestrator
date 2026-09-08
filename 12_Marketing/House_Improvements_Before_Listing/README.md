# House Improvements Before Listing

## TL;DR
- Buyers decide in roughly three seconds on the portal scroll. Spend where the eye lands first: lead photograph, curb appeal, lighting. Paint, landscaping and professional photography return more than kitchen, bathroom or pool spend.
- The Fields framework organises buyer journey into three layers: what they **see** (Layer 1, drives the click), what they **feel** (Layer 2, drives the offer), what they **compare** (Layer 3, drives the price).
- Industry data points (paint 25% faster sale / up to 5% price; professional photos 118% more views, 32% faster sale; twilight images up to 76% more views; curb appeal up to 7% of sale price) are consistent across NAR, VHT Studios, Zillow, the Johnson/Tidwell/Villupuram 2019 hedonic study and Fields' own Burleigh Waters DOM analysis.

## What the Book Says
Chapter 5 of *Before You List* ("The Three Things That Actually Move the Price", pp.54-63) builds a three-layer model from 60 academic studies, 14 peer-reviewed papers and 2,153 sold Gold Coast properties.

**Layer 1 — What buyers see first.** The realestate.com.au scroll is the gatekeeper. If the lead image fails, nothing else loads: floor plan unseen, copy unread, $45,000 kitchen invisible. Highest-ROI pre-sale spending lives here — paint, landscaping, professional photography, virtual tours.

**Layer 2 — What buyers feel.** Specific, vivid descriptions activate mental simulation; the buyer pictures their Saturday afternoon on the north-facing deck. This is the endowment effect — once mental ownership starts, willingness to pay rises and price sensitivity falls. Generic descriptions ("4-bed family home with pool") describe hundreds of properties; specific descriptions ("the 8-minute walk to Robina State School follows the canal path") describe one. Manufactured urgency backfires: Fields' own Burleigh Waters analysis found urgency-style openers had an average 33 days on market vs 20.5 days for factual openers — 61% longer.

**Layer 3 — What buyers compare.** No property is valued alone. Honest, quantified trade-offs ("540 sqm vs Robina average ~740 sqm — that's roughly $220,000 the buyer is not paying, not despite the smaller block, because of it") give buyers control, and a buyer in control makes an offer.

**Where renovation fits.** Big-ticket renovations (kitchen ~57% ROI, bathroom ~75%, pool 0.6-3.7% per sqm) live in Layer 2, not Layer 1. They support the offer once the click has happened. In Robina and Varsity Lakes, renovated stock showed *lower* price per sqm than original-condition (book notes a likely floor-area confounder — larger homes have lower $/sqm and are also more often renovated). In Burleigh Waters, renovation added approximately 14% per sqm because the buyer pool (established professionals, downsizers) values turnkey.

**Appendix A** is the checklist — exterior (sweep, pressure-wash, weed, mow, repair gate, exterior lights), kitchen (clear benchtops, deep clean appliances, organise drawers), bathrooms (spotless, regrout if discoloured, eliminate mould), living areas (declutter, clean windows, clear sight lines), outdoor living (pressure-wash deck, pool clear, trim view lines, stage transition from indoors), throughout (fresh paint, fix taps and sticky doors, replace bulbs, professional clean before photography).

## Internal Data & Evidence

- **Burleigh Waters DOM analysis** — listings with urgency-style opening lines averaged 33 days on market vs 20.5 days for factual data-driven openers (book p.56-57, derived from Fields positioning research, 2,153 sold properties).
- **Sale stock analysed:** 2,153 sold properties across the southern Gold Coast; 60 academic studies and 14 peer-reviewed papers synthesised in the playbook. See `001_Our_Competitive_Advantages/research/positioning_guide_summary_from_drive.md` and `~/.claude/projects/.../memory/positioning_research.md`.
- **Renovation by suburb finding — SUPERSEDED 2026-09-09:** the book's claim (Robina/VL renovated stock *lower* $/sqm; BW +14%) was re-derived with full controls (`16_Valuation/Renovation_Premium/renovation_premium_study.py`). The Robina negative sign WAS the floor-area confounder: controlled, fully-renovated Robina houses show **+11.7%** (p=0.0001), BW **+16.1%** (confirmed, likely understated), Varsity +6.9% (ns). Suburb *ranking* survives (BW ~10pp above Robina, p=0.002); only `fully_renovated` carries a premium — cosmetic/partial price like original. Premium ≠ ROI (cost unobserved). See `16_Valuation/Renovation_Premium/REPORT_2026-09-09.md`.
- **Suburb medians used in framework:** Robina $1,400,000; Varsity Lakes $1,224,000; Burleigh Waters $1,710,000 (book p.58).
- **Will's local photography library** — `Will954633/fields-local-photography` (referenced in `CLAUDE.md` and `fb-photo-manager.py`). Sunday sync from this repo into `system_monitor.photo_inventory`.
- **Local production discipline** — Fields filming/production guide (`memory/filming_production_guide.md`) sets visual brand standards: consistent colour grading, eye contact, scene-cut cadence — the same principles transfer to stills (consistent grade across a listing set).
- **Sarah and Mark vignette (book p.60)** — anonymised Robina case. $45,000 kitchen renovation; agent's three calls were free furniture repositioning on the deck, an ~$800 garden refresh (Begonia 'White Ice' ribbon, recut bed edges, fresh dark mulch over existing Carissa hedge / Alcantarea anchor / Crotons), and leading photos with the backyard not the kitchen. Outcome: facade photographed dramatically better; jacaranda twilight image generated 14 inspection groups in the analogous Will's-view example.
- **Property page imagery flow** — `PropertyPage.tsx` and AI photo classification (`iteration_08` step 105, floor plan step 106) score and order photos for the website detail page. The hero selection logic is the in-house equivalent of "lead image discipline".

## Academic & Research Foundation

> **Johnson, E. B., Tidwell, A., & Villupuram, S. V. (2020).** Valuing Curb Appeal. *The Journal of Real Estate Finance and Economics*, 60(1), 111-133. https://link.springer.com/article/10.1007/s11146-019-09713-z (also https://ideas.repec.org/a/kap/jrefec/v60y2020i1d10.1007_s11146-019-09713-z.html)
> Uses Google Street View images, deep-learning classification and hedonic controls. Finds own-property curb appeal worth roughly twice that of an across-the-street neighbour; combined own + neighbour curb appeal can account for up to 7% of sale price. Premium is more pronounced in weak markets and in neighbourhoods with already-high average curb appeal.

> **Des Rosiers, F., Thériault, M., Kestens, Y., & Villeneuve, P. (2002).** Landscaping and House Values: An Empirical Investigation. *Journal of Real Estate Research*, 23(1-2), 139-162. https://www.tandfonline.com/doi/abs/10.1080/10835547.2002.12091072
> Field-survey hedonic study of 760 single-family homes (Quebec Urban Community, 1993-2000). Positive tree-cover differential vs neighbourhood (provided not excessive) lifts value; high lawn cover, flower arrangements, rock plants and hedges command substantial premiums; the visible-surrounding tree-cover effect is amplified in areas with high proportions of retired residents.

> **Soleymanian, M., & Qian, Y. (2024).** From Novelty to Norm: Uncovering the Drivers of Virtual Tour Effectiveness in Real Estate Sales. *NBER Working Paper* No. 33204. https://www.nber.org/papers/w33204 / SSRN: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5040538
> Analyses ~75,000 Los Angeles home sales linking MLS records, assessor data and agent marketing. Virtual tours raise sale price by ~1% on average; effect has declined post-COVID as tours moved from novelty to norm; benefit is larger in competitive markets and for less-experienced agents, smaller for highly differentiated properties.

> **Kahneman, D., Knetsch, J. L., & Thaler, R. H. (1990).** Experimental Tests of the Endowment Effect and the Coase Theorem. *Journal of Political Economy*, 98(6), 1325-1348. https://www.journals.uchicago.edu/doi/10.1086/261737
> Foundational endowment-effect work. The willingness-to-accept / willingness-to-pay gap that the book invokes in Layer 2 originates here and in subsequent Thaler papers.

> **Tomasik, B. et al. (Real Estate Management and Valuation, 2023).** How to weaken the endowment effect in the housing market? The role of behavioral interventions. https://www.remv-journal.com/How-to-weaken-the-endowment-effect-in-the-housing-market-The-role-of-behavioral-interventions,193129,0,2.html
> Confirms endowment-effect operates in housing transactions; demonstrates that exposure to comparable market-price data and visual reference points reduces (does not eliminate) the gap.

> **Bucchianeri, G. W., & Minson, J. A. (2013).** A homeowner's dilemma: Anchoring in residential real estate transactions. *Journal of Economic Behavior & Organization*, 89, 76-92. https://www.sciencedirect.com/science/article/abs/pii/S0167268113000644
> Listing price anchors final sale price; this underpins the book's Layer 3 argument that competitive context (what other properties are listed *right now*) sets the bracket buyers compare against.

## Other Quality References

- **National Association of Realtors — 2023 Profile of Home Staging** — https://www.nar.realtor/research-and-statistics/research-reports/profile-of-home-staging — 81% of buyer's agents say staging makes it easier for buyers to visualise the home; 20% report staging adds 1-5% to offered value; 48% of seller's agents report staging cuts time on market.
- **NAR 2024 Profile of Home Buyers and Sellers** — https://www.nar.realtor/research-and-statistics/research-reports/highlights-from-the-profile-of-home-buyers-and-sellers — buyer behaviour benchmarks.
- **VHT Studios (NAR-aligned)** — homes shot professionally sell 32% faster, listings receive 118% more online views. https://legacy.vht.com/news/professional-photography-sells-homes-faster.aspx
- **Zondahome / Remodeling Magazine — 2024 Cost vs Value Report** — https://zondahome.com/the-2024-cost-vs-value-report-proves-curb-appeal-still-drives-highest-value-for-home-improvement-projects/ — curb appeal items (garage door, manufactured stone veneer, exterior paint) top the ROI table; mid-range kitchen ~71%, mid-range bath ~74%, major kitchen ~41.8%, upscale kitchen ~52.6%, upscale bath ~45%.
- **Matterport / RIS Media — 3D tour study** — https://matterport.com/blog/3d-tours-properties-sell-31-faster-and-higher-price — listings with Matterport sold up to 9% higher and up to 31% faster (multi-market MLS analysis + paired-CMA study).
- **Project EverGreen / Virginia Tech extension — Landscape value research** — https://www.pubs.ext.vt.edu/426/426-087/426-087.html — survey-based finding that sophisticated landscaping lifts perceived home value ~12%.
- **Redfin — Twilight photography** — https://www.redfin.com/blog/twilight-photography-and-listing-your-home/ — industry data on twilight imagery as a hero shot.

## Marketing Content Ideas

| # | Hook | Audience | Anchor Data | Format | Editorial Check |
|---|------|----------|-------------|--------|-----------------|
| 1 | "The three-second rule: how Robina buyers actually choose what to inspect" | Seller, agent-shopper | 118% more views with pro photography (VHT/NAR); Fields' three-layer model | Long-form article (1,200 words) on `/articles/` | Data only, no "you should". OK. |
| 2 | "An $800 garden refresh vs a $45,000 kitchen — what the data says" | Seller | Sarah & Mark vignette; Fields renovation ROI table | FB carousel post (5 cards) | No valuation references in headline. No advice — describe outcomes. OK. |
| 3 | "Listings in Burleigh Waters that opened with urgency averaged 33 days on market. Listings that opened with facts averaged 20.5." | Seller, agent-shopper | Fields Burleigh Waters DOM analysis | FB single-image post | Factual. Cite "Fields analysis of Burleigh Waters listings". OK. |
| 4 | "The Layer 1 checklist: every item that affects the scroll" | Active seller | Appendix A | Lead-magnet PDF (1-page) | Practical, no advice. OK. |
| 5 | "Why renovation ROI differs by suburb on the southern Gold Coast" | Pre-sale seller | Fields suburb-level finding (Robina/VL/BW); caveat about floor-area confounder | Article on `/market-intelligence/:suburb` | Must include caveat. OK. |
| 6 | "What buyers see, feel, compare — the 3-layer property positioning framework" | All sellers | Chapter 5 framework | Reel series (3 x 15s) | One concept per reel. OK. |

## Open Questions / Gaps

- ~~**Floor-area confound in Robina/VL renovation finding**~~ — **RESOLVED 2026-09-09**: rerun with full controls refuted the negative Robina sign (it was the confounder; controlled premium is +11.7%). "Renovation reduces value in Robina" must never be asserted — it is false. Book Chapter 5 "suburb exception" paragraph needs revision at next reprint. See `16_Valuation/Renovation_Premium/REPORT_2026-09-09.md`.
- **Verify the "5% offer uplift from fresh paint" figure** — widely cited (HomeGain, Zillow paint-colour studies show ~7% discount on unpainted vs painted) but no single peer-reviewed source. Currently marked as industry consensus, not academic.
- **Local photography A/B** — Fields could test lead-image variants (interior vs hero exterior vs twilight) on its own `/for-sale` listings via PostHog feature flag.
- **Twilight stat 47% higher $/sqft, 76% more views** — cited by SmartPhotoEditors / Captivly; original source chain is industry blogs, not academic. `[NEEDS VERIFICATION]` before publishing.
- **Australian-specific staging ROI** — most academic and industry data is US. A 5-listing pilot through a Gold Coast stager (paired CMA) would give us local numbers.

See `references.md` for the consolidated URL list.
