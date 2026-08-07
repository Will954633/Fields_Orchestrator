# E2 — What should this business be doing to get leads that it is not doing?

The single binding constraint: **inbound enquiry**. Traffic exists and is growing, but almost nobody
contacts us. The North Star metric is an inbound enquiry from a homeowner.

What we know from our own data, which you should verify rather than accept:

- ~91% of traffic arrives from Google organic, overwhelmingly as bare-address searches ("12 Smith St
  Robina") landing on a single property page. Most visitors view exactly ONE address and leave.
- We generate off-market "discovery decks" at `/off-market/:slug` — roughly 14,600 pages indexed.
- We have an "Analyse Your Home" conversion page, a Facebook lead funnel (**paused**), a Messenger
  auto-responder, a fridge-magnet QR landing page, and an owner-article generator that produces a
  printed appraisal posted to a specific address.
- A previous internal audit concluded that direct mail — the middle step of the whole strategy — **has
  never actually run**, so the inbound funnel has never been properly tested. Tens of thousands of
  decks exist and, per that audit, zero homes were physically touched. Verify whether that is still true.
- The public will not hand over a phone number or email. Capturing a physical **address** and posting
  something is the strategy that fits the audience.

Your job: find the highest-value thing we are not doing, or are doing wrong.

Look at the actual machinery, not just the strategy documents — `scripts/` for lead handling, CRM sync,
lead intelligence, the nightly lead chain, Messenger and Facebook integrations, PostHog analytics
helpers, and the website's conversion surfaces. Check whether the things we believe are running are
in fact running: `system_monitor` collections and `logs/` will tell you, and `system_monitor.job_runs`
holds heartbeats for self-registered jobs. A funnel step that silently stopped months ago is a more
valuable finding than a clever new idea.

Specific questions worth answering, if the evidence supports it:

1. Is there a measurable drop-off point where interested owners are lost? Where exactly?
2. Of the conversion surfaces that exist, which are actually reachable by a real visitor arriving on a
   property page from Google? Trace the path.
3. Is anything capturing intent signals that nobody ever acts on? Unread queues are common here.
4. What would you do first with one week of effort, and what evidence makes you confident?

Be concrete about mechanism, not just aspiration. "Improve conversion" is not a finding. "Owners who
scroll to the valuation section have no reachable next step because X" is.
