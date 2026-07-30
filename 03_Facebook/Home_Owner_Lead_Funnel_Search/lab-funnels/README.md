# /lab/ — Home Owner Funnel-Discovery lab (off-brand, out-of-market)

Static, instrumented landing pages served at `https://vm.fieldsestate.com.au/lab/<variant>/`.
Build 6C of `03_Facebook/Home_Owner_Lead_Funnel_Search/04_EXPANDED_MANDATE_SCOPING.md`.

## Hard rules
- **NOINDEX.** nginx sends `X-Robots-Tag: noindex, nofollow, noarchive` on `/lab/`, and every
  page also carries `<meta name="robots" content="noindex, nofollow">`. This content must
  **never** be crawled or associated with the Gold Coast brand.
- **No raw PII to analytics.** `lab_harness.js` sends only `{field, valid}` on completion, and
  for email only `{email_domain}` (for junk detection). Actual PII values never reach PostHog.
- **Honest end-states only.** Terminal is `deadend` ("not live in your area yet") until the
  Brisbane market-newsletter exists; only then does `waitlist_optin` (a real server-side email
  capture) turn on. No promise the flow can't keep.
- **Templates are Will-gated.** A new template goes to Will as a preview link + spec before any
  ad traffic (§8). Copy tweaks within an approved template stay autonomous.

## Event spine (contract with the reward ledger)
Every page includes `/lab/lab_harness.js`, which emits, carrying `variant` + `lab_cid`:

| event | when | key props |
|-------|------|-----------|
| `lab_lp_view` | page load | variant, step=0 |
| `lab_step_view` | a step becomes visible | variant, step, step_name |
| `lab_field_focus` | user focuses a PII field | variant, field |
| `lab_field_complete` | valid value entered (blur) | variant, field, valid, email_domain? |
| `lab_micro_conversion` | a sub-goal reached | variant, goal ∈ {address,email,name,phone} |
| `lab_call_cta_click` | "call us" CTA clicked | variant |
| `lab_terminal` | end reached | variant, terminal_type ∈ {deadend,waitlist_optin} |

## Building a template
Declarative (preferred) — add data-attributes, include the harness:
```html
<body data-lab-variant="AN2_progressive_v1">
  <div data-lab-step="1" data-lab-step-name="ask-name"><input data-lab-field="name"></div>
  <button data-lab-micro="name">Continue</button>
  <div data-lab-terminal="deadend">…</div>
  <script src="/lab/lab_harness.js"></script>
</body>
```
Or call the `window.Lab.*` API directly. See `_selftest/index.html`.

The ledger sync (`ledger/ledger_sync.py`, cron hourly) pulls these into
`system_monitor.funnel_events`; `ledger/compute_reward.py` scores each variant.
