# "Win a Tinny" — Meta Instant Form + Campaign Spec (QLD-gated)

**Purpose:** capture **name + phone + address** from a broad QLD/Gold-Coast audience via a free prize
draw, with the express consent needed to lawfully follow up about property services. Then filter
owner-occupied vs leased in-house. See `LEGAL_COMPLIANCE_BRIEF.md` and `TERMS_AND_CONDITIONS_DRAFT.md`.

---

## 1. Instant Form

**Form name:** `Tinny Giveaway — QLD (name+phone+address, consent)`
**Form type:** **More Volume** (fast submit) — note the required consent tickboxes add one screen.

### Fields
| Field | Type | Prefill | Required |
|---|---|---|---|
| First name | `FIRST_NAME` (standard) | ✅ auto (profile) | yes |
| Phone number | `PHONE` (standard) | ✅ auto (when on profile) | yes |
| Residential street address | `CUSTOM` (free text) | ❌ (can't prefill) | yes |

*(Address is a custom field — it's the property address, so Meta can't prefill it. It's mandatory: it
gates QLD eligibility and prize delivery, and it's the asset the whole campaign exists to capture.)*

### Context card (intro)
- **Headline:** `Win a tinny 🚤`
- **Body:** `We're giving away a [make/model] tinny to one lucky Gold Coast local. Enter free — just
  confirm your details. Open to Queensland residents aged 30+. Full terms apply.`
- **Small print in body:** `This promotion is not sponsored, endorsed or administered by Meta,
  Facebook or Instagram. See full Terms & Conditions and our Privacy Policy below.`
- **Button:** `Enter the draw`

### Consent & eligibility (Meta "custom disclaimer" with required tickboxes)
Add a **custom disclaimer** block with **two required checkboxes** (entry cannot submit unless both are
ticked). This is the legal core — it carries express consent for calls/SMS/email + the eligibility
declaration, and Meta timestamps it.

- **Disclaimer title:** `Please confirm`
- **Checkbox 1 (required):**
  `I am a Queensland resident aged 30 or over, and I've read the Terms & Conditions and Privacy Policy.`
- **Checkbox 2 (required):**
  `I consent to Fields contacting me by phone, SMS and email about property services and this
  giveaway. I can opt out anytime (reply STOP / unsubscribe).`
- **Links in the disclaimer:** Terms & Conditions → `[T&Cs landing page URL]` · Privacy Policy →
  `https://fieldsestate.com.au/privacy`

> Consent must be **express, specific and retained** (Do Not Call Register Act + Spam Act + Privacy
> Act). Export the lead records (which include the consent + timestamp) and store them for **5 years**.

### Privacy policy
`https://fieldsestate.com.au/privacy` (link_text: "Privacy Policy") — required by Meta and APP 5.

### Thank-you screen
- **Headline:** `You're in the draw! 🎣`
- **Body:** `Good luck — we'll draw the winner on [draw date] and contact you if you win. Curious what
  your own home is worth in today's market? Take a look.`
- **Button:** `See my home's value` → `https://fieldsestate.com.au/analyse-your-home` *(optional second
  step — keeps the property angle without cluttering entry).*

---

## 2. Campaign structure

- **Objective:** Leads → Instant Form (destination on-ad), optimise `LEAD_GENERATION`.
- **Special Ad Category:** `[]` (a *giveaway* — not Housing). ⚠ Keep the **creative about the boat**,
  not a valuation/real-estate service, or Meta may reclassify it and strip targeting.
- **Placements:** Reels + Stories (vertical), optionally Feed for volume.
- **Budget:** `[$X]/day`, start **PAUSED**.
- **CTA button:** `Sign Up` (Meta's closest to "Enter").

### Targeting (broad-capture model — per Will's plan)
- **Location:** Queensland / Gold Coast (people who **live** here). *Eligibility is still gated in the
  T&Cs to QLD 30+ — targeting alone isn't enough.*
- **Age:** 30–65. **Gender:** all.
- **Interests (optional refinement / test):** Boating, Fishing, Boats, Home improvement, Gardening.
- **Exclusions:** existing lead/customer custom audiences (don't pay to re-collect).
- **Advantage+ audience:** on (broad; interests as suggestions).

### Primary text (ad copy) — sells the boat, discloses nothing misleading
`🚤 WIN A TINNY. We're giving one away to a lucky Gold Coast local. Free to enter — QLD residents 30+.
Enter in 15 seconds. T&Cs apply. Not sponsored by Meta.`

**Headline:** `Win a tinny — enter free`

---

## 3. Pre-launch checklist (do NOT activate until all ticked)

- [ ] T&Cs finalised + **solicitor-reviewed**, hosted at a stable URL; link live.
- [ ] Prize details confirmed (make/model/value/inclusions) in T&Cs + form.
- [ ] Promotion dates + draw date/location set; **redraw** clause dated.
- [ ] Form built with **address (required)** + **both consent tickboxes required** + T&C/Privacy links.
- [ ] Meta disclaimer present; **no share/tag mechanics**.
- [ ] Ad targeted QLD/GC; **eligibility gated in T&Cs**.
- [ ] Lead export → CRM wired; **consent + timestamp retained (5 yrs)**.
- [ ] Follow-up SMS/email carries **sender ID + unsubscribe/STOP**; opt-outs suppressed.
- [ ] Real-estate follow-up script is **POA-compliant** (Form 6 before acting for a seller).
- [ ] `ad_decisions` logged on create; built **PAUSED** for review.

---

## 4. Build note

When approved, this can be built with a launcher modelled on `03_Facebook/Reels/launch_reel_leads.py`
(swap the form definition for the one above — add the required **address** custom field and the
**custom_disclaimer** consent block — and the boat creative). Everything created **PAUSED** and logged,
same as the Reel3 lead ad.
