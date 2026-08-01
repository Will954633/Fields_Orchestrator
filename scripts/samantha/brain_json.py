#!/usr/bin/env python3
"""
brain_json.py — robust JSON extraction from LLM output, shared across all three brains.

WHY THIS EXISTS
---------------
Four separate call sites each hand-rolled their own "find the JSON in the model's reply"
logic, and every one of them fails on a different, common model behaviour:

  brain1_deep.decompose  :  re.search(r"\\[.*\\]", out, re.S)   -- GREEDY
  brain1_deep._judge_chunk: re.search(r"\\[.*\\]", out, re.S)   -- GREEDY
  brain3_annotate         :  s[s.find("[") : s.rfind("]")+1]   -- outermost-span
  brain2/ad_annotate      :  s[s.find("{") : s.rfind("}")+1]   -- outermost-span

The greedy regex spans from the FIRST "[" to the LAST "]" in the whole response. If the model
emits two arrays, or an array followed by prose containing a bracket, the captured span is not
valid JSON. `json.loads` then raises "Extra data: line N column 1" -- which is exactly the
observed production failure:

    [judge] FAIL-OPEN (kept all 18): Extra data: line 7 column 1 (char 47)

The outermost-span variants fail the same way for the same reason.

STRATEGY (in order, first success wins)
---------------------------------------
  1. direct json.loads of the whole stripped response  (the happy path)
  2. fenced code block  ```json ... ```                (very common Haiku/Opus behaviour)
  3. balanced-bracket scan                             (correct span, string/escape aware)

The balanced scan is the real fix: it tracks nesting depth and ignores brackets inside string
literals, so it returns the FIRST COMPLETE value and stops -- it cannot over-capture trailing
prose. Where several top-level arrays are present it returns the largest complete one, which is
the right choice for the judge (the model sometimes emits a short example array first).

Used by brain1_deep.py (facets + judge), brain3_annotate.py, brain2/ad_annotate.py.
"""
import json
import re

_FENCE = re.compile(r"```(?:json|javascript|js)?\s*(.+?)```", re.S | re.I)


def _scan_balanced(text, open_ch, close_ch):
    """Yield every COMPLETE top-level {..} / [..] span in `text`, string- and escape-aware.

    Unlike a greedy regex this stops at the matching close bracket, so trailing prose,
    a second array, or a stray bracket in commentary can never be swallowed into the span.
    """
    depth = 0
    start = None
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == open_ch:
            if depth == 0:
                start = i
            depth += 1
        elif ch == close_ch:
            if depth:
                depth -= 1
                if depth == 0 and start is not None:
                    yield text[start:i + 1]
                    start = None


def _candidates(text, open_ch, close_ch):
    """Ordered parse candidates: whole text, then fenced blocks, then balanced spans."""
    t = (text or "").strip()
    if t:
        yield t
    for m in _FENCE.findall(t):
        m = m.strip()
        if m:
            yield m
    # largest complete span first: models sometimes emit a tiny illustrative array before the
    # real one, and the real answer is essentially always the longer of the two.
    spans = sorted(_scan_balanced(t, open_ch, close_ch), key=len, reverse=True)
    for s in spans:
        yield s


def _load(text, open_ch, close_ch, want):
    for cand in _candidates(text, open_ch, close_ch):
        try:
            val = json.loads(cand)
        except Exception:
            continue
        if isinstance(val, want):
            return val
    raise ValueError(
        f"no parseable JSON {'array' if want is list else 'object'} in model output "
        f"({len(text or '')} chars, starts: {(text or '')[:80]!r})"
    )


def parse_json_array(text):
    """Extract a JSON array from LLM output. Raises ValueError if none is parseable."""
    return _load(text, "[", "]", list)


def parse_json_object(text):
    """Extract a JSON object from LLM output. Raises ValueError if none is parseable."""
    return _load(text, "{", "}", dict)


def parse_with_retry(prompt, call, want="array", retry_suffix=None, on_retry=None):
    """Call the model, parse; on a parse failure retry ONCE with an explicit format reminder.

    `call` is any callable(prompt) -> text. A transient parse failure otherwise permanently
    costs that batch its result (for the judge, that meant fail-open on a whole batch).

    Returns the parsed value. Raises ValueError if both attempts fail, so the caller keeps
    ownership of its own failure policy (e.g. the judge's deliberate fail-open).
    """
    parser = parse_json_array if want == "array" else parse_json_object
    shape = "JSON array" if want == "array" else "JSON object"
    try:
        return parser(call(prompt))
    except Exception as first:
        if on_retry:
            on_retry(first)
        suffix = retry_suffix or (
            f"\n\nIMPORTANT: your previous reply could not be parsed. Reply with ONLY a valid "
            f"{shape} and NOTHING else — no preamble, no explanation, no code fences, no text "
            f"after the closing bracket."
        )
        try:
            return parser(call(prompt + suffix))
        except Exception as second:
            raise ValueError(f"parse failed twice: {first} | retry: {second}") from second


if __name__ == "__main__":
    # Regression cases — each of these breaks at least one of the four hand-rolled parsers.
    cases = [
        ('["a","b"]', ["a", "b"]),
        ('Here you go:\n["a","b"]\nHope that helps!', ["a", "b"]),                 # trailing prose
        ('```json\n["a","b"]\n```', ["a", "b"]),                                   # fenced
        ('["x"]\n\n["a","b","c"]', ["a", "b", "c"]),                               # two arrays -> largest
        ('["a [not an id]","b"]', ["a [not an id]", "b"]),                         # bracket in string
        ('["u0001","u0002"]\nThese units cover [see above] the topic.', ["u0001", "u0002"]),
        ('[\n  "a"\n]\nExtra data: line 7 column 1', ["a"]),                       # the prod failure
    ]
    ok = True
    for raw, want in cases:
        try:
            got = parse_json_array(raw)
        except Exception as e:
            got = f"RAISED {e}"
        flag = "ok " if got == want else "FAIL"
        ok &= got == want
        print(f"[{flag}] {raw[:44]!r:48} -> {got}")
    obj_cases = [
        ('{"a":1}', {"a": 1}),
        ('Sure:\n{"a":1}\nDone.', {"a": 1}),
        ('```json\n{"a":{"b":2}}\n```', {"a": {"b": 2}}),
        ('{"note":"use {braces} freely"}', {"note": "use {braces} freely"}),
    ]
    for raw, want in obj_cases:
        try:
            got = parse_json_object(raw)
        except Exception as e:
            got = f"RAISED {e}"
        flag = "ok " if got == want else "FAIL"
        ok &= got == want
        print(f"[{flag}] {raw[:44]!r:48} -> {got}")
    print("\nALL PASS" if ok else "\nFAILURES ABOVE")
