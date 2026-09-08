#!/usr/bin/env python3
"""
retime_beats.py — re-time the walkthrough ink BEATS to a new video's caption timeline.

Every suburb's walkthrough uses the SAME narration script (only the numbers differ), so each
ink beat is anchored to a STRUCTURAL trigger phrase. Given a new suburb/month's
`*_walk_segments.txt` (captions already synced to that video), this resolves each beat's new
time from where its trigger phrase appears, and prints a `remap={old_t:new_t,...}` dict to paste
into the swap step (see ASSET_REPLACEMENT.md).

Usage:
  python3 retime_beats.py /path/to/<suburb>_walk_segments.txt
Trigger phrases are structural (not suburb-specific numbers/months), so the same map works for
Robina / Varsity Lakes / Burleigh Waters. Circle POSITIONS are read from live chart geometry at
runtime, so they auto-adapt; only the TIMES come from here.
"""
import re, json, sys

# (old_t baseline [Robina], trigger substring in the narration | None, offset seconds, ref_label)
# None trigger => derive from the named ref beat + offset (docks, camera-offs, fades).
BEATS = [
 ("intro_stage",        0,   None, 0, None),
 ("dom_enter",          23,  "how long it takes a house to sell", 0, None),
 ("dom_dock",           29,  None, 6, "dom_enter"),
 ("dom_label",          35,  "days on market metric", 0, None),
 ("dom_label_fade",     44,  None, 9, "dom_label"),
 ("dom_june",           48,  "days in june", 1, None),
 ("dom_aug",            51,  "end of august", 0, None),
 ("dom_rel",            84,  "the lower the buyer demand", 0, None),
 ("dom_rel_fade",       90,  None, 6, "dom_rel"),
 ("dom_symptom",        110, "symptom of the current market", 0, None),
 ("bridge_stage",       120, "move fairly gradually", -3, None),
 ("bridge_box1",        127, "the share markets do", 0, None),
 ("bridge_box2",        134, "last six months", 0, None),
 ("median_enter",       156, "in median house prices", 0, None),
 ("median_dock",        160, None, 4, "median_enter"),
 ("median_gradual",     164, "gradual decline", 0, None),
 ("median_peak",        170, "we've had our peak", 2, None),
 ("median_latest",      175, "come down to", 0, None),
 ("asking_enter",       186, "asking prices changing in this market", 0, None),
 ("asking_dock",        192, "exactly what we have in this chart", 0, None),
 ("asking_labels",      198, "the actual asking price of homes", 0, None),
 ("asking_labels_fade", 214, "look over the historical period", -2, None),
 ("cam_hist_zoom",      216, "look over the historical period", 0, None),
 ("cam_hist_pan",       221, "look over the historical period", 7, None),
 ("cam_hist_off",       230, "december 2023", -2, None),
 ("asking_dec2023",     236, "december 2023", 0, None),
 ("asking_sept2026",    250, "september 2026", 0, None),
 ("cam_recent",         255, "september 2026", 2, None),
 ("cam_recent_off",     263, "starting to recognise", -3, None),
 ("asking_sellers",     266, "adjust their listing prices", 0, None),
 ("withdrawn_enter",    285, "number of homes that get withdrawn", 0, None),
 ("withdrawn_dock",     291, "what we can see in this chart", 0, None),
 ("withdrawn_didntsell",300, "prior to the gfc", 0, None),
 ("withdrawn_2025",     326, "take a look at 2025", 2, None),
 ("withdrawn_2026",     334, "already in 2026", 0, None),
 ("withdrawn_trend",    350, "trend has definitely changed", 0, None),
 ("leading_stage",      368, "move in a different direction", 0, None),
 ("leading_signal",     380, "moves before the market", 0, None),
 ("lending_enter",      402, "exactly what we get in this next chart", 0, None),
 ("lending_dock",       408, "new house lending", 2, None),
 ("lending_cba",        414, "reserve bank of australia", 0, None),
 ("lending_leads",      420, "12 months before house prices", 0, None),
 ("lending_settings",   435, "select all data available", 0, None),
 ("lending_3yr",        479, "click on the three year view", 0, None),
 ("lending_recent",     510, "what are we seeing more recently", 0, None),
 ("lending_20",         513, "showing at 20", 0, None),
 ("lending_10",         520, "dropped in half down to 10", 0, None),
 ("lending_cam_off",    530, None, 9, "lending_20"),
 ("lending_directional",548, "none of these are certain", 0, None),
 ("close_stage",        583, "three data points here", 0, None),
 ("close_dom",          591, "days on market is shooting up", 0, None),
 ("close_withdrawn",    599, "number of homes being withdrawn", 0, None),
 ("close_lending",      607, "still declining still moving lower", 0, None),
 ("close_flat",         622, "flat line to declining", 0, None),
]

def norm(s): return re.sub(r'[^a-z0-9 ]','',s.lower())

def main(path):
    txt = open(path, encoding="utf-8").read()
    segs = json.loads(re.search(r'\[\s*\[.*\]\s*\]', txt, re.S).group(0))
    nsegs = [(float(t), norm(x)) for t, x in segs]
    resolved = {}
    warned = []
    # first pass: phrase-anchored beats
    for label, old_t, trig, off, ref in BEATS:
        if trig is None: continue
        key = norm(trig)
        hit = next((st for st, nt in nsegs if key in nt), None)
        if hit is None:
            warned.append((label, trig)); resolved[label] = None
        else:
            resolved[label] = round(hit + off, 2)
    # second pass: derived beats (ref + offset)
    for label, old_t, trig, off, ref in BEATS:
        if trig is not None: continue
        if ref is None: resolved[label] = 0.0
        else: resolved[label] = round((resolved.get(ref) or 0) + off, 2)
    # build remap old_t -> new_t, enforce ascending
    remap = {}
    prev = -1
    for label, old_t, trig, off, ref in BEATS:
        nt = resolved.get(label)
        if nt is None: nt = old_t  # unmatched: keep old (and warn)
        if nt < prev: nt = prev    # monotonic guard
        remap[old_t] = nt; prev = nt
    print("remap=" + json.dumps(remap, separators=(',', ':')))
    if warned:
        print("\n# UNMATCHED TRIGGERS (kept old time — check the narration wording):", file=sys.stderr)
        for lbl, tr in warned: print(f"#   {lbl}: '{tr}'", file=sys.stderr)
    else:
        print("\n# all triggers matched", file=sys.stderr)

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "robina_2026-08_dom_walk_segments.txt")
