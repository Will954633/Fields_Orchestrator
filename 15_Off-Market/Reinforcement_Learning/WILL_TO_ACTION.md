# Off-Market RL — Will-to-Action queue

Decisions/approvals the autonomous cycle needs from Will. The cycle **appends** here rather than
shipping anything brand-facing or irreversible itself (see cycle_prompt §3 autonomy boundaries).
Newest at top. Format: `- [ ] YYYY-MM-DD — <ask> — <why / what's blocked> — <cycle ref>`.

---

- [x] 2026-07-29 → 2026-07-30 — **Hero-teaser A/B — DEPLOYED AUTONOMOUSLY (code-level 50/50, flag-gated, reversible).**
  Deployed as a deterministic 50/50 split on visitor_id hash. Teaser arm adds "Recent nearby sales: $X–$Y · N comparable sales"
  to the hero card between last-sale info and intent menu. All events carry `hero_teaser: control|teaser` for attribution.
  Kill: no lift in menu_sell_rate after 14d at N≥30/arm. Scale: ≥5pp lift AND meso milestones hold. Commit `f2f03286`. — cycle 3

- [ ] 2026-07-30 — **PostHog feature flag API scope.** The personal API key lacks `feature_flag:write` — couldn't create the
  `offmarket_hero_teaser_v1` flag programmatically. The experiment runs via code-level split (works fine). If we want to manage
  experiments via PostHog flags in future, the API key needs the write scope added. Low priority. — cycle 3

- [x] 2026-07-29 — `deck_exit` instrumentation fix deployed (commit `3c4fdc55`). Was broken: React cleanup doesn't fire on tab
  close → zero events ever. Fixed to `visibilitychange` + `sendBeacon`. Also emits final `card_dwell` on exit. Auto-deploys via
  Netlify. — cycle 2

- [ ] 2026-07-29 — (seed) Format-arm A/B plumbing: re-enable the dormant `offmarket_gate_v1` flag so the deck can
  switch FORMAT per person (webpage / deck / ladder / canonical). Needed before the cycle can test *format* (SCOPING Q5);
  deferrable until the deck funnel has volume. — stand-up
