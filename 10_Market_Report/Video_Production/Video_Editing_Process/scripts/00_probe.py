#!/usr/bin/env python3
"""
Stage 00 — probe the raw clips → work/manifest.json

Reads every video in the configured raw_dir, records duration / resolution / fps /
audio, and orders them by their DJI timestamp (filename encodes YYYYMMDDhhmmss), i.e.
the order they were shot — the natural first-pass narrative order.

Usage:  python3 scripts/00_probe.py [--config config.yaml]
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vlib  # noqa: E402

HERE = Path(__file__).resolve().parent.parent


def load_config(p: str) -> dict:
    import yaml
    return yaml.safe_load((HERE / p).read_text()) if not Path(p).is_absolute() else yaml.safe_load(Path(p).read_text())


def dji_ts(name: str):
    m = re.search(r"(\d{14})", name)
    return m.group(1) if m else name


def main():
    vlib.load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    args = ap.parse_args()
    cfg = load_config(args.config)

    raw_dir = (HERE / cfg["paths"]["raw_dir"]).resolve()
    work = (HERE / cfg["paths"]["work_dir"]).resolve()
    work.mkdir(parents=True, exist_ok=True)

    clips = sorted(
        [p for p in raw_dir.iterdir() if p.suffix.lower() in (".mp4", ".mov", ".m4v")],
        key=lambda p: dji_ts(p.name),
    )
    if not clips:
        raise RuntimeError(f"no raw clips found in {raw_dir}")

    manifest = {"raw_dir": str(raw_dir), "clips": []}
    total = 0.0
    for c in clips:
        s = vlib.probe_summary(str(c))
        s["name"] = c.name
        s["shot_ts"] = dji_ts(c.name)
        manifest["clips"].append(s)
        total += s["duration"]
        print(f"  {c.name:<42} {s['duration']:7.1f}s  {s['width']}x{s['height']} "
              f"{s['fps']}fps  a:{s['acodec']} {s['sample_rate']}Hz/{s['channels']}ch")
    manifest["total_duration"] = round(total, 1)
    print(f"  {'—'*42} {total:7.1f}s TOTAL  ({total/60:.1f} min) across {len(clips)} clips")

    out = work / "manifest.json"
    out.write_text(json.dumps(manifest, indent=2))
    print(f"\n✓ wrote {out}")


if __name__ == "__main__":
    main()
