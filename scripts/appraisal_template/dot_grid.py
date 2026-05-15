"""SVG dot-grid generator for cohort-comparison visuals.

Used by section_01_right and any future section that visualises a cohort
proportion. Deterministic: same `seed` + same `total`/`highlighted_count`
always produces the same SVG, so re-renders match prior versions exactly.

Design tokens match V4 (`09_Appraisals/Version_Four/preview.html`):
    --copper: #B76749   highlighted dots
    --neutral: #d8cfc1  inert dots (matches V4 muted backgrounds)
"""

from __future__ import annotations

import hashlib
import math
import random
from typing import Optional

# V4 design tokens
COPPER = "#B76749"
NEUTRAL = "#c9b9a0"  # slightly darker than --copper-soft so dots are readable on cream bg


def render(
    total: int,
    highlighted_count: int,
    cols: Optional[int] = None,
    seed: Optional[str] = None,
    *,
    dot_radius: float = 1.4,
    highlight_radius: float = 2.0,
    spacing: float = 5.5,
    margin: float = 4.0,
    copper: str = COPPER,
    neutral: str = NEUTRAL,
) -> str:
    """Return SVG markup for a dot grid.

    Args:
        total: number of dots in the grid (the universe count).
        highlighted_count: how many dots to render in the highlight colour.
        cols: optional column count. Defaults to a near-square grid.
        seed: optional string seed for deterministic placement of highlighted
            dots. Use the subject_id so re-renders are reproducible.
        dot_radius, highlight_radius: mm.
        spacing: mm between dot centres.
        margin: mm padding around the grid.
    """
    if total <= 0:
        return ""
    if cols is None:
        cols = max(1, math.ceil(math.sqrt(total) * 1.05))  # very slightly wider than tall
    rows = math.ceil(total / cols)

    width = margin * 2 + cols * spacing
    height = margin * 2 + rows * spacing

    # Deterministic random placement
    if seed:
        h = int(hashlib.sha256(seed.encode()).hexdigest()[:16], 16)
        rng = random.Random(h)
    else:
        rng = random.Random(42)
    highlighted = set(rng.sample(range(total), min(highlighted_count, total)))

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}mm" height="{height}mm" '
        f'viewBox="0 0 {width:.2f} {height:.2f}" '
        f'role="img" aria-label="{highlighted_count} of {total} dot grid">'
    ]
    for i in range(total):
        col = i % cols
        row = i // cols
        cx = margin + col * spacing + spacing / 2
        cy = margin + row * spacing + spacing / 2
        if i in highlighted:
            parts.append(
                f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{highlight_radius:.2f}" '
                f'fill="{copper}" />'
            )
        else:
            parts.append(
                f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{dot_radius:.2f}" '
                f'fill="{neutral}" />'
            )
    parts.append("</svg>")
    return "\n".join(parts)
