"""Appraisal template system — programmatic generators for V4 appraisal sections.

Built 2026-05-15 as the foundation for the 90/10-split template system.
Every function here is a pure transform from `subject_id` (or subject doc) to a
render payload. Substantiation files are written by `substantiation.py`; rendering
to HTML/PDF is downstream.

Modules:
    data_pull       — section-specific data assemblers (Section 01 right, etc.)
    pick_highlight  — auto-rank candidate highlight attributes by catchment rarity
    substantiation  — dual-write substantiation files (Mongo + flat JSON)
    dot_grid        — SVG dot-grid generator
"""
