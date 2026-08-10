#!/usr/bin/env python3
"""
Override Protocol voice lines.

Reuses the EXACT voice and processing chain from
15_Off-Market/Page_Redesign_V3/outro/build_voice.py — en-GB-Studio-C, pitch -2,
rate 1.0, and the same lowpass/chorus/echo/compressor/loudnorm filter that makes
it read as a ship's computer. Imported rather than copied so the two surfaces
cannot drift into sounding like different systems.

Long and short variants of the middle line are both generated: measured TTS runs
~13.5 chars/sec, so the full line costs ~3.6s and pushes the sequence past the
6-second target. Will picks after hearing both.
"""
import importlib.util, sys
from pathlib import Path

SRC = Path("/home/fields/Fields_Orchestrator/15_Off-Market/Page_Redesign_V3/outro/build_voice.py")
spec = importlib.util.spec_from_file_location("bv", SRC)
bv = importlib.util.module_from_spec(spec)
sys.argv = ["bv"]                      # stop its argparse running on import
spec.loader.exec_module(bv)

bv.LINES = [
    ("ov1",      "Override accepted."),
    ("ov2long",  "Restricted property intelligence channel opening."),
    ("ov2short", "Restricted channel open."),
    ("ov3",      "Samantha online."),
    ("ovend",    "Priority channel closed."),
    # alternates for the other two tonal versions Will listed
    ("altA1",    "Priority protocol engaged."),
    ("altA2",    "Property response channel established."),
    ("altB1",    "Archive lock disengaged."),
    ("altB2",    "Property records access granted."),
]

out = Path(__file__).parent / "voice"
bv.build_set(bv.DEFAULT_VOICE, out, 1.0, -2.0, "Override Protocol")
