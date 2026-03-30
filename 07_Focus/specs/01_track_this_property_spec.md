# Conversion Spec: Track This Property

## Goal
- Capture buyer-intent emails on property pages with one low-friction utility CTA.
- Target conversion rate: 5-8% from module views to successful email submit.

## Benchmark Rules Applied
- One offer only.
- One field only.
- 6th-grade reading level.
- Keep the module short enough to fit above the fold on desktop and near-above-the-fold on mobile.

## Recommended Default Variant
- **Headline:** Track this property
- **Subheading:** Get an email if the price changes or it goes under offer.
- **Button label:** Track updates
- **Form fields:** Email
- **Success message:** You're tracking this home. We'll email you if the price changes or the status updates.

## Placement
- Show one inline module on every property page.
- Desktop: place in the right rail inside the top summary block, directly below the price / key facts / valuation proof.
- Mobile: place directly under the top summary block and before long-form analysis, photos below fold, or similar-property modules.
- Do not open a modal.
- Do not repeat the same CTA again lower on the page.

## UX Notes
- Email field placeholder: `Enter your email`
- Button should submit inline.
- Add one small trust line under the button: `No spam. Only updates for this home.`
- Track events: module_view, email_submit, submit_success.

## Copy Variants To Test

### Variant A: Direct utility
- **Headline:** Track this property
- **Subheading:** Get an email if the price changes or it goes under offer.
- **Button label:** Track updates
- **Why test it:** Most literal version. Best fit if users already understand the page.

### Variant B: Outcome-first
- **Headline:** Never miss a price change
- **Subheading:** We will email you when this home's price or sale status changes.
- **Button label:** Email me updates
- **Why test it:** Stronger immediate value for cold traffic.

### Variant C: Lighter commitment
- **Headline:** Keep me posted on this home
- **Subheading:** Get simple email updates for price drops and status changes.
- **Button label:** Keep me posted
- **Why test it:** Softer tone may reduce resistance on mobile and paid traffic.

## Guardrails
- Use only one CTA in the module.
- No extra checkbox.
- No extra explainer copy.
- No address field, phone field, or account creation.
- If the property is already sold or under contract, hide this CTA.

## Friday Review Metrics
- Primary: submit conversion rate from module views
- Secondary: submit count, property page bounce change, property page scroll depth, lead reply rate

## Sprint Call
- CONTINUE
