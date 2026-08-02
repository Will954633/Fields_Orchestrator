# QR Code Capabilities — getting a link off our screen and onto their phone

**Status:** concept + working measurement rig. Nothing shipped, nothing pushed, no
QR code exists anywhere in the codebase today (`grep -rilE "qrcode|qr_code|qrserver"`
over `scripts/`, `src/`, `netlify/` returns nothing).
**Rig:** [generate_qr.py](generate_qr.py) — builds all seven payload variants and
decodes each one back to verify it round-trips. Samples in [samples/](samples/).

---

## The gap this answers

The Discovery deck **already has a save row** — SMS, WhatsApp, Messenger — at
`src/pages/OffMarketPage/discovery/DiscoveryDeck.tsx:412-416`:

```ts
const saveMsg = `Hi Will — keeping my off-market plan for ${doc.address_short} handy. My link: ${SITE}/off-market/${doc.slug}`;
const saveLinks = {
  sms:       `sms:+61416529481?&body=${encodeURIComponent(saveMsg)}`,
  whatsapp:  `https://wa.me/61416529481?text=${encodeURIComponent(saveMsg)}`,
  messenger: `https://m.me/889412530933297?ref=${encodeURIComponent(doc.slug)}`,
};
```

That row solves the problem **only when the visitor is already holding their own
phone.** Every one of those is a tap-through on the device the deck is running on.

The QR case is the opposite situation: **the deck is on our screen** — Will's iPad
at a door, a laptop at a kitchen table, a monitor at an appraisal. The save row is
physically unreachable. There is no path today from our screen to their phone that
doesn't involve asking for a phone number out loud, which
[[contact_capture_reality_and_address_mail_strategy]] established the public
won't give.

**So a QR here is not a convenience feature. It is the only bridge across a device
boundary we currently cannot cross.** That reframes the whole evaluation: the
question is not "which QR looks nicest", it's *which payload survives the handoff
and leaves something behind.*

---

## The core failure mode

A QR that encodes a plain URL opens a browser tab. The tab dies, the link is gone,
and we learn nothing about who scanned. It is the default choice and the worst one.

Everything worth building either **(a)** lands the link in an app that persists, or
**(b)** trades the scan for a channel we own. Sorted by how much survives:

| Tier | Payload | What survives on their phone | Do we learn who they are |
|---|---|---|---|
| 0 | Plain URL | Browser history. Effectively nothing. | No |
| 1 | vCard / MECARD | A contact card with the URL in it, permanently | No |
| 1 | Calendar `VEVENT` | A dated event carrying the URL | No |
| 2 | `SMSTO:` prefilled | The sent SMS thread, searchable forever | **Their mobile number** |
| 2 | `mailto:` prefilled | Their sent-mail | **Their email** |
| 3 | `m.me/<page>?ref=<slug>` | A Messenger thread with the link auto-replied | **A PSID we can message again** |
| 4 | Wallet pass (`.pkpass`) | An object in Wallet we can **update later** | Only if issued post-identification |

Tiers 1 and 2 need **zero backend**. Tier 3 is already built. Tier 4 is the only
one that costs money.

---

## Measured: payload size decides whether it scans off a screen

This is the part that is usually guessed at and shouldn't be. A longer payload
forces a higher QR version, more modules, finer detail — and a code a camera
cannot resolve off a glossy screen at arm's length. Measured by
[generate_qr.py](generate_qr.py), all at error correction level M:

| Payload | Bytes | QR version | Modules | Min render width | Round-trip |
|---|---|---|---|---|---|
| `messenger` | 57 | 4 | 33 | **16 mm** | PASS |
| `url` | 63 | 5 | 37 | 18 mm | PASS |
| `mecard` | 162 | 9 | 53 | 26 mm | PASS |
| `sms` | 164 | 9 | 53 | 26 mm | PASS |
| `whatsapp` | 176 | 9 | 53 | 26 mm | PASS |
| `mailto` | 209 | 10 | 57 | 28 mm | PASS |
| `vcard` | 265 | 12 | 65 | **32 mm** | PASS |

"Min render width" = modules × 0.5 mm, the conservative floor for a module edge
scanned off a **screen** at ~30 cm. Print tolerates finer; screens do not — glare
and subpixel rendering eat the margin.

Two things fall out of this table:

1. **The Messenger payload is the smallest code on the list *and* the only one
   with a server behind it.** It carries just a slug, not a message. That is a rare
   case of the highest-capability option also being the most robust one physically.
2. **vCard is nearly twice the module count of Messenger** for the same
   information. If a contact card is wanted, use **MECARD** (162 bytes vs 265) —
   identical "Add to Contacts" behaviour, a materially coarser and more scannable
   code. There is no reason to ship full vCard 3.0 here.

Practical rule for on-screen display: render at **at least 3× the minimum** above
(so ~50 mm for Messenger, ~100 mm for vCard), keep the 4-module quiet zone the rig
enforces, and turn screen brightness up. A QR flush against the deck's black
chrome will not acquire at all.

---

## What each payload does natively on the phone

| Payload | iOS Camera | Android (Lens / camera) | Confidence |
|---|---|---|---|
| URL | Opens Safari | Opens Chrome | Certain |
| vCard / MECARD | Offers "Add to Contacts" | Offers "Add contact" | High — **not phone-tested, see below** |
| `SMSTO:` | Opens Messages, body prefilled | Opens default SMS app | High |
| `mailto:` | Opens Mail, prefilled | Opens Gmail | High |
| `tel:` | Offers to call | Offers to call | Certain |
| `VEVENT` | Inconsistent | Inconsistent | **Low — do not rely on** |
| `m.me/…` | Opens Messenger app if installed, else web | Same | High |

`VEVENT` is listed for completeness only. Handling varies enough between OS
versions that it should not carry the primary link.

---

## Add to Home Screen is currently broken for this purpose

Worth stating plainly because it looks like it works.

`index.html:9` links `/site.webmanifest`, and that file is live (HTTP 200) and
valid — `display: standalone`, 192px and 512px maskable icons, correct theme
colour. So an "Add to Home Screen" produces a proper app-style icon.

**But `start_url` is `"/"` and `scope` is `"/"`.** An owner who adds the page to
their home screen from `/off-market/5-chantilly-place-robina` gets an icon that
opens **the Fields homepage, not their house page.** As a mechanism for saving
*this link*, it does the wrong thing — it saves the site.

Fixing it means a per-property manifest (`start_url` pointed at the deck URL,
`short_name` set to the street address) served dynamically and referenced with a
route-level `<link rel="manifest">`. That is a small Netlify function, not a
rebuild. Until then, Add to Home Screen should not be offered as a "save your
link" action, because it doesn't.

> Local-tree note: `public/site.webmanifest` is **absent from
> `/home/fields/Feilds_Website/01_Website/public/`** but present in the GitHub
> repo at `public/site.webmanifest` (637 bytes) and served live. Consistent with
> [[git_local_drift_gh_api]] — the local tree is not the source of truth. Verify
> against `gh api`, not the filesystem, before concluding a public asset is
> missing.

---

## Wallet passes — the only durable, *updatable* artifact

Apple Wallet (`.pkpass`) and Google Wallet generic passes are the only option here
that puts a persistent object on the phone that **we can change afterwards**. A
pass carries a link, sits in Wallet indefinitely, can be push-updated (a changed
comparable range, a new sold nearby), and can surface on the lock screen near a
location.

For an audience that won't give a phone number, a Wallet pass is the closest thing
to an owned channel that requires no contact details at all — the pass update
token *is* the address.

Costs, honestly: Apple Developer Program (~$99/yr) plus a Pass Type ID certificate
and signing; Google Wallet needs a GCP service account and issuer approval.
Roughly a day of build for both. It should not be the first thing built, but it is
the correct end state, and it's the only item on this page that would make the
off-market deck *re-openable* weeks later without an email address.

---

## Recommendation

**Make the QR a Messenger deep-link, not a URL.**

`https://m.me/889412530933297?ref=<slug>` wins on every axis measured here:

- **Smallest code on the list** (33 modules, 16 mm floor) — the most forgiving to
  scan off a bright screen at conversational distance.
- **The backend already exists.** `netlify/functions/messenger-webhook.mjs`
  (183 lines, live) reads the `ref` from all three delivery shapes
  (`messaging_referral`, `postback.referral`, `message.referral`), auto-replies
  with the visitor's deck link via the Send API, logs the lead, and pings Will on
  Telegram. Zero new infrastructure.
- **It's the only option that leaves a two-way channel** in the Page inbox — not a
  personal phone — which we can re-open later.
- The link arrives in a **thread**, which is permanent and searchable, rather than
  a tab.

Fall back to **`SMSTO:`** for anyone without Messenger — same trade, gives a mobile
number instead of a PSID, at 53 modules instead of 33.

Offer **MECARD** as the passive third option for people who won't engage with
either — it costs nothing, needs no backend, and at minimum leaves our number and
the URL on their phone.

Order of build: Messenger QR (hours) → SMS fallback (hours) → per-property
manifest fix (half a day) → Wallet pass (a day, and only if the first three show
real scan volume).

---

## Analytics

The Messenger route is already instrumented at the *tap* end — `plan_message_channel`
with `conversion_channel` — see [[offmarket_discovery_deck_analytics]]. A QR scan
is a different event because it crosses devices, and reusing the same event name
would silently corrupt the existing channel metrics.

| Event | When | Why it matters |
|---|---|---|
| `qr_displayed` | QR rendered on our screen | denominator — how often we actually present it |
| `qr_scanned` | webhook receives a `ref` tagged as QR-sourced | **the only real measure of whether QR works in person** |
| `qr_channel` | `{messenger \| sms \| contact}` | which payload people actually pick |

The `ref` should carry a source marker (`<slug>__qr`) so a QR scan is
distinguishable from an on-device tap of the same Messenger button. Without that
marker the two are indistinguishable at the webhook and the whole question stays
unmeasurable. `extractRef()` in the webhook would need to split the suffix back off
before resolving the slug.

---

## Compliance notes

- **An inbound message is not marketing consent.** A scan that opens SMS or
  Messenger gives us a reply channel for *that conversation*. Treating it as
  opt-in for ongoing sends is a separate question and a Spam Act one — worth
  Will's call before anything automated messages these contacts a second time.
- The prefilled SMS/WhatsApp body is a message sent **as the visitor**, so it must
  not assert anything on their behalf. The current `saveMsg` copy is clean.
- Anything the QR lands on inherits the house rules —
  [[feedback_no_advice_data_only]], [[feedback_no_valuation_in_headlines]]. The
  deck already complies; a Wallet pass showing a figure would need a **range**,
  per [[valuation_method_comparables]].
- [[listed_vs_offmarket_guard]] applies unchanged: a QR pointing at a house that
  has since listed must not present an off-market plan.

---

## Open questions for Will

1. **Where is this QR actually shown?** The whole design changes depending on
   whether it's on an iPad at a door (one-to-one, we can talk them through it), on
   the deck itself for cross-device save (self-serve), or printed on the mailed
   appraisal (print tolerates far denser codes, so vCard becomes viable).
2. **Messenger or SMS as the primary?** Messenger gives the better long-term
   channel and the more scannable code; SMS gives a phone number, which is what
   the direct-mail strategy actually wants. They capture different things.
3. **Is a Wallet pass worth $99/yr** before we know anyone scans anything? My view:
   no — build it after the Messenger QR shows real `qr_scanned` volume.
4. **Do we fix `start_url` regardless?** It's a genuine defect for any owner who
   tries to save their page today, independent of whether we ever ship a QR.

---

## Files

| File | What |
|---|---|
| `generate_qr.py` | Payload builder + round-trip verifier. `--slug`, `--out`, `--scale`. |
| `samples/*.png` | One rendered QR per payload type, slug `5-chantilly-place-robina`. |
| `README.md` | This document. |

**Verification done:** all seven payloads generated and **decoded back to their
exact input** (pyzbar primary, OpenCV `QRCodeDetector` fallback) — no payload
round-trip failed. Module counts and QR versions read from the symbol itself, not
estimated. `messenger.png` rendered and inspected visually. Live manifest fetched
and parsed (HTTP 200, `start_url: "/"` confirmed). Webhook line count and `ref`
handling read from source. Slug taken from the live sitemap, not invented.

**Not done — and load-bearing:** *nothing has been scanned with a real phone.*
Round-tripping through a decoder library proves the payload is well-formed; it does
**not** prove an iPhone camera at 30 cm off a lit screen will acquire it, and it
does not confirm the vCard "Add to Contacts" prompt actually appears on current
iOS. Those two claims are the ones the whole recommendation rests on and they need
a five-minute test with an actual handset before anything is built. No React
component, no integration with either deck, nothing pushed to GitHub.
