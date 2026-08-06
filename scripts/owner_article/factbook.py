#!/usr/bin/env python3
"""
factbook.py -- the numeric-honesty mechanism for the owner-subject article.

Why this exists
---------------
A draft of the prototype shipped the phrase "four of the eight" when the true
count was six. In a format whose entire value proposition is numerical honesty,
a wrong number is not a typo -- it is the product failing at the one thing it
claims to do. Proof-reading does not scale to hundreds of addresses.

So the fix is structural rather than procedural. Every number that reaches the
page must be MINTED here first:

    fb = FactBook()
    fb.money("adj_low", 1172211)      -> "$1,172,211"   (and records it)
    fb.pct("movement", 5.8)           -> "+5.8%"        (and records it)

Copy is then written using only those returned strings. Afterwards `verify()`
re-scans the finished text for anything that looks like a figure and asserts it
was minted. A number that was typed by hand, copied from an older draft, or
survived a template edit has no mint record and fails the build.

This cannot catch a number that is minted from wrong INPUT -- that is the
selection layer's job. It catches the entire class of "the prose and the data
disagree", which is the one that actually bit us.
"""
from __future__ import annotations

import re

# Tokens that look numeric but are never claims about the market.
# Kept deliberately small: the safe failure is a false alarm, not a silent pass.
_ALWAYS_OK = {
    # ordinals/counts that appear in fixed copy furniture
    "1", "2",
}

# A year on its own (1900-2099) is a date reference, not a market figure.
_YEAR = re.compile(r"^(19|20)\d{2}$")

# What counts as "a figure" in finished copy.
_TOKEN = re.compile(
    r"""
      \$\d{1,3}(?:,\d{3})*(?:\.\d+)?   # $1,172,211 -- grouped, so a trailing
                                       # sentence comma is not swallowed
    | [-+]?\d+(?:\.\d+)?\s?%           # +5.8%  /  -2.0%  / 47%
    | \b\d[\d,]*(?:\.\d+)?\b           # bare numbers: counts, sqm, km, years
    """,
    re.VERBOSE,
)


class FactMintError(RuntimeError):
    pass


class FactBook:
    """Mints formatted figures and remembers every string it emitted."""

    def __init__(self):
        self._emitted: set[str] = set()
        self._by_key: dict[str, object] = {}

    # ---------- minting ----------

    def _emit(self, key: str, raw, text: str) -> str:
        prior = self._by_key.get(key)
        if prior is not None and prior != raw:
            raise FactMintError(
                f"fact {key!r} minted twice with different values: {prior!r} then {raw!r}"
            )
        self._by_key[key] = raw
        self._emitted.add(text)
        # A figure is often re-stated without its symbol ("8 sales" then "the eight").
        # Register the bare numeric core too so verification is about VALUES, not glyphs.
        self._emitted.add(text.lstrip("+-$").rstrip("%").strip())
        return text

    def money(self, key: str, value) -> str:
        v = int(round(float(value)))
        return self._emit(key, v, f"${v:,}")

    def pct(self, key: str, value, signed: bool = True, dp: int = 1) -> str:
        v = round(float(value), dp)
        sign = "+" if (signed and v > 0) else ""
        return self._emit(key, v, f"{sign}{v:.{dp}f}%")

    def num(self, key: str, value, dp: int = 0) -> str:
        f = float(value)
        text = f"{f:,.{dp}f}" if dp else f"{int(round(f)):,}"
        return self._emit(key, round(f, dp), text)

    def word_count(self, key: str, value: int) -> str:
        """Counts we also spell out ('eight sales' ... 'the eight')."""
        words = {
            1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
            7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve",
        }
        n = int(value)
        self._emit(key, n, str(n))
        w = words.get(n)
        if w:
            self._emitted.add(w)
        return w or str(n)

    def address(self, key: str, text: str) -> str:
        """A street address. Its digits are identifiers, not market claims --
        '81 Thorngate Drive' must not be read as the figure 81."""
        self._by_key[key] = text
        for tok in _TOKEN.findall(text):
            self._emitted.add(tok.strip())
            self._emitted.add(tok.lstrip("+-$").rstrip("%").strip())
        self._emitted.add(text)
        return text

    def date(self, key: str, text: str) -> str:
        """Dates are facts too; register their numeric parts as allowed."""
        self._by_key[key] = text
        for tok in _TOKEN.findall(text):
            self._emitted.add(tok.strip())
            self._emitted.add(tok.lstrip("+-$").rstrip("%").strip())
        self._emitted.add(text)
        return text

    def allow_literal(self, text: str) -> str:
        """Escape hatch for externally-sourced copy (the macro block), whose
        figures carry their own source attribution in the data file."""
        for tok in _TOKEN.findall(text):
            self._emitted.add(tok.strip())
            self._emitted.add(tok.lstrip("+-$").rstrip("%").strip())
        return text

    # ---------- verification ----------

    def value(self, key: str):
        return self._by_key.get(key)

    def verify(self, text: str) -> list[str]:
        """Return every figure in `text` that was never minted. Empty == clean."""
        unminted = []
        for raw in _TOKEN.findall(text):
            tok = raw.strip()
            core = tok.lstrip("+-$").rstrip("%").strip()
            if tok in self._emitted or core in self._emitted:
                continue
            if core in _ALWAYS_OK or _YEAR.match(core):
                continue
            unminted.append(tok)
        return sorted(set(unminted))
