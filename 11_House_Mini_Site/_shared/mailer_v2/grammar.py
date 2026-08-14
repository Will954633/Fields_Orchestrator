#!/usr/bin/env python3
"""
grammar.py — every dynamic claim also has a grammatical state.

The V2 findings are all data-driven counts, and a sentence that reads correctly
for n=6 can be wrong, or merely absurd, for n=1 or n=0:

    "The 1 listing a buyer would realistically choose between"
    "1 Home for sale that closely compete with yours"
    "3 buyers may weigh against it"

Three of those shipped past review this session, each fixed individually. They
kept recurring because the rule was being applied per template rather than in
one place. This module is that one place.

A count is not a number, it is one of three STATES — zero / one / many — and
every dependent word in the surrounding sentence changes with it:

    that home        / those homes
    it               / they
    its price        / their prices
    the property     / the properties
    compare with     / choose between      <- you cannot choose between one thing

Usage:

    c = Count(len(homes))
    f"{c.word} {c.noun('home', 'homes')} {c.verb('competes', 'compete')} with yours"
    c.pick(zero="Nothing competes", one="One home competes", many=f"{c.n} homes compete")
"""
from __future__ import annotations

# Numbers written as words read better in prose than numerals, up to the point
# where the numeral is doing the work ("Only 12 homes"). Cards and headlines use
# `n` directly; running sentences use `word`.
_WORDS = {0: "no", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
          6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}


class Count:
    """A number plus the grammar that has to agree with it."""

    def __init__(self, n: int):
        self.n = int(n or 0)

    # ---- state ----------------------------------------------------------
    @property
    def state(self) -> str:
        return "zero" if self.n == 0 else "one" if self.n == 1 else "many"

    @property
    def is_one(self) -> bool:
        return self.n == 1

    @property
    def is_zero(self) -> bool:
        return self.n == 0

    def pick(self, zero, one, many):
        """Choose a whole phrasing per state. Use this when the sentence
        SHAPE changes, not just a word — which is most of the time."""
        return {"zero": zero, "one": one, "many": many}[self.state]

    # ---- words that must agree -----------------------------------------
    @property
    def word(self) -> str:
        """'no' / 'one' / 'two' … / '12' — for running prose."""
        return _WORDS.get(self.n, str(self.n))

    def noun(self, singular: str, plural: str) -> str:
        return singular if self.n == 1 else plural

    def verb(self, singular: str, plural: str) -> str:
        """Note the inversion: a SINGULAR subject takes the 's' form
        ('one home competes'), a plural subject does not ('six homes compete').
        Getting this backwards is the '1 Home … that closely compete' bug."""
        return singular if self.n == 1 else plural

    @property
    def is_are(self) -> str:
        return "is" if self.n == 1 else "are"

    @property
    def that_those(self) -> str:
        return "That" if self.n == 1 else "Those"

    @property
    def it_they(self) -> str:
        return "it" if self.n == 1 else "they"

    @property
    def its_their(self) -> str:
        return "its" if self.n == 1 else "their"

    def the_noun(self, singular: str, plural: str) -> str:
        """'the property' / 'the properties'."""
        return f"the {self.noun(singular, plural)}"

    @property
    def compare_phrase(self) -> str:
        """You cannot 'choose between' one thing."""
        return "compare with yours" if self.n == 1 else "choose between"

    def __int__(self):
        return self.n

    def __repr__(self):
        return f"Count({self.n}:{self.state})"
