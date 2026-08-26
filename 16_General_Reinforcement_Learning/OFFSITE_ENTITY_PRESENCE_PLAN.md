# Off-site entity presence — drafting pack (paste-and-verify)

**Created:** 2026-08-27 · **Owner split:** Will creates/verifies the accounts; Claude drafts
the copy (below) and wires the on-site `sameAs` schema once the live URLs exist.

**Why this exists:** our `RealEstateAgent` entity's entire off-site footprint is Facebook +
Instagram. LLMs describe Fields as "a data company" and resolve "Will Simpson + real estate +
Gold Coast" to a **different** Will Simpson (at Phillis Real Estate) because he has years of
third-party corroboration and we have none. This pack builds that corroboration and
disambiguates our Will.

---

## 0. CANONICAL ENTITY BLOCK — use these values IDENTICALLY everywhere

Consistency is the signal. Same name, same phrasing, same licence, same suburbs on every
profile. Never vary the business name (not "Fields Estate", not "Fields Research" — the
company is **Fields Real Estate**).

| Field | Canonical value |
|---|---|
| Business name | **Fields Real Estate** |
| Principal / agent | **Will Simpson** |
| Licence | **Licensed Real Estate Agent, QLD Licence No. 4832972** |
| Area served | **Southern Gold Coast — Robina, Varsity Lakes, Burleigh Waters** |
| Website | **https://fieldsestate.com.au** |
| Email | will@fieldsestate.com.au |
| Membership | Member, Real Estate Institute of Queensland (REIQ) |
| Phone | **[WILL TO PROVIDE — must be identical on every profile]** |
| Address / service area | **[WILL: storefront address, or run as a service-area business]** |

> **Disambiguation rule:** wherever "Will Simpson" appears, pair it with **"Fields Real
> Estate"** and **"QLD Licence No. 4832972"** in the same sentence or field. That triplet is
> what separates our Will from the Phillis namesake in an entity graph.

**Rule 5 note:** all copy below is data/fact only — no advice, no predictions, no valuation
figures, no forbidden words. "Licensed Queensland real estate agency" is fact (licence 4832972,
already asserted in our site-wide schema).

---

## 1. Google Business Profile  ★ highest leverage

Feeds the Google Knowledge Graph, "real estate agent [suburb]" results, AI Overviews and Gemini.

- **Business name:** Fields Real Estate
- **Primary category:** Real estate agency
- **Additional categories:** Real estate consultant · Real estate appraiser *(we produce
  appraisals/valuations — defensible; do NOT add "Property management" — we don't do it)*
- **Area served:** Robina, Varsity Lakes, Burleigh Waters, and the surrounding southern Gold
  Coast. *(If no public storefront, set it up as a **service-area business** — no street
  address shown, suburbs listed as service areas.)*
- **Website:** https://fieldsestate.com.au
- **Appointment/URL:** https://fieldsestate.com.au/analyse-your-home
- **Phone / hours:** [WILL]

**Description (≤750 chars, paste as-is):**

> Fields Real Estate is a licensed Queensland real estate agency selling homes on the southern
> Gold Coast — Robina, Varsity Lakes and Burleigh Waters. Founded by Will Simpson (Licensed
> Real Estate Agent, QLD Licence No. 4832972), the agency pairs local expertise with original
> property data and transparent methodology: every valuation, market report and property page
> cites its sources and its limits. Buyers get free market intelligence and comparable-sales
> analysis; sellers get honest, evidence-based positioning of their home. Member of the Real
> Estate Institute of Queensland.

**Services to list:** Residential sales · Property appraisals · Comparable-sales analysis ·
Market reports · Seller positioning.

---

## 2. RateMyAgent  ★ directly answers the query that beat us

The agent queries returned RateMyAgent-style directories (top3realestateagents.com.au), not us.

**Agency profile — Fields Real Estate**
- Location: Southern Gold Coast, QLD
- Website: https://fieldsestate.com.au
- Description: use the GBP description above (verbatim — consistency).

**Agent profile — Will Simpson**
- Title: **Principal · Licensed Real Estate Agent (QLD Licence No. 4832972)**
- Agency: Fields Real Estate
- Bio (paste):

> Will Simpson is the founder and principal of Fields Real Estate, a licensed Queensland
> agency selling homes on the southern Gold Coast — Robina, Varsity Lakes and Burleigh Waters.
> He built the agency around original property data: transparent, source-cited valuations and
> market analysis that give buyers and sellers the same evidence. QLD Licence No. 4832972;
> member of the Real Estate Institute of Queensland.

---

## 3. realestate.com.au + Domain  (authoritative AU sources — need agency access)

These are the sources LLMs treat as authoritative for "is X a real estate agency in Australia."
Both generally require an active agency subscription/admin — **[WILL: confirm access]**.

**Agency listing — Fields Real Estate:** name, southern Gold Coast, website, logo, GBP
description verbatim.

**Agent profile — Will Simpson** (both platforms, same bio):

> Will Simpson, Principal of Fields Real Estate — a licensed Queensland agency (QLD Licence No.
> 4832972) selling homes in Robina, Varsity Lakes and Burleigh Waters. Will's approach is
> data-first: buyers and sellers get transparent, source-cited valuations and market analysis,
> not marketing. Member, Real Estate Institute of Queensland.

---

## 4. LinkedIn  (free — strongest person-entity disambiguator)

**Company page — Fields Real Estate**
- Industry: **Real Estate**
- Tagline: *Licensed Gold Coast real estate agency. Smarter with data.*
- Specialties: Residential sales, Property valuation, Market analysis, Southern Gold Coast
- About: GBP description verbatim.
- Website: https://fieldsestate.com.au

**Will's personal profile**
- **Headline:** *Founder & Principal, Fields Real Estate | Licensed Real Estate Agent, QLD
  Licence No. 4832972 | Gold Coast*
- **About (paste):**

> Founder and principal of Fields Real Estate, a licensed Queensland real estate agency
> (Licence No. 4832972) selling homes on the southern Gold Coast — Robina, Varsity Lakes and
> Burleigh Waters. I built Fields around original property data: transparent, source-cited
> valuations and market intelligence that give buyers and sellers the same evidence. Member,
> Real Estate Institute of Queensland.
- **Experience entry:** Principal · Fields Real Estate · Gold Coast (link to the company page).

*(The headline is the highest-value single field — it's what pins "Will Simpson" to Fields
Real Estate + licence 4832972 in LinkedIn's and the LLMs' person graph.)*

---

## 5. On-site connective tissue — STAGED (Claude ships once URLs exist)

Standing authorisation (geo brief §4: entity markup). **Not applied yet** — a dead `sameAs` is
a worse signal than none. Send me the live URLs and I add, in one commit, to the
`RealEstateAgent` node in `src/root.tsx` (and mirror in `public/about.html`):

```jsonc
"sameAs": [
  "https://www.facebook.com/889412530933297",      // existing
  "https://www.instagram.com/fieldsestate.com.au/", // existing
  "<GBP maps/place URL>",
  "<RateMyAgent agency URL>",
  "<realestate.com.au agency URL>",
  "<Domain agency URL>",
  "<LinkedIn company page URL>"
]
```

Plus a `Person` node for Will with **his** `sameAs` (LinkedIn personal, RateMyAgent agent, REA
agent) so the *person* entity is disambiguated, not just the org.

---

## Sequencing

1. **This week (free, no gatekeeper):** Google Business Profile · RateMyAgent · LinkedIn.
2. **When agency access confirmed:** realestate.com.au + Domain.
3. **As each goes live:** send Claude the URL → schema `sameAs` updated same day.
4. **Grade:** re-run the three GEO-018 identity queries after re-index (~4 weeks from the last
   profile going live) — target is the "data company / not an agency / wrong Will Simpson"
   framing flipping to a licensed-agency characterisation.
