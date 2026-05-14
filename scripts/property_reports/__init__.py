"""
Property Reports — backend pipeline for the House Mini-Site engine.

Modules:
- slot_resolver: queries Gold_Coast + precomputed market collections to
  produce per-property data for the mini-site. One method per slot.
- build_property_report: CLI orchestrator. Reads a stub property_reports
  doc by slug, resolves slots, writes back, transitions state.
- poller: long-running loop that finds stub docs and triggers
  build_property_report against each one.

State transitions:
    stub  ──(slot_resolver runs)──>  under_review  ──(consultant signs off)──>  final  ──(time)──>  living
"""
