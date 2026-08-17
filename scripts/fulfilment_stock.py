#!/usr/bin/env python3
"""
fulfilment_stock.py — what Pronto Direct is actually holding, and what is left.

Balance is COMPUTED from two sources and never stored, so it cannot drift:

    on_hand   = sum(receipts in config/fulfilment_flows.yaml)
                - pieces on work orders with status "posted"
    available = on_hand
                - pieces on work orders that are prepared/sent but NOT yet posted

The reserved half matters. A work order sitting at "prepared" has not consumed an
envelope yet, but the envelope is spoken for — counting only "posted" would let two
batches be planned against the same 100 envelopes, and the second would fail at
Pronto rather than here.

⚠ Only items WE supply are stock. The mailer is printed per job by Pronto from our
PDFs, so paper is never counted.

Usage
  python3 scripts/fulfilment_stock.py                # current position
  python3 scripts/fulfilment_stock.py --plan 50      # can we run 50 more pieces?
"""
from __future__ import annotations
import argparse
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from shared.db import get_client  # noqa: E402

REGISTRY = os.path.join(ROOT, "config", "fulfilment_flows.yaml")
CONSUMED_STATUSES = {"posted"}
RESERVED_STATUSES = {"prepared", "sent_to_supplier", "printing"}


def position(db=None):
    cfg = yaml.safe_load(open(REGISTRY))
    stock = cfg.get("stock") or {}
    db = db if db is not None else get_client()["system_monitor"]

    consumed_pieces = reserved_pieces = 0
    by_order = []
    for wo in db["fulfilment_work_orders"].find({}):
        n = wo.get("pieces") or len(wo.get("items") or [])
        st = (wo.get("status") or "prepared").lower()
        if st in CONSUMED_STATUSES:
            consumed_pieces += n
        elif st in RESERVED_STATUSES:
            reserved_pieces += n
        by_order.append((wo.get("flow_code"), n, st))

    out = {}
    for name, item in stock.items():
        received = sum(r.get("qty", 0) for r in (item.get("receipts") or []))
        per = item.get("per_piece", 1)
        on_hand = received - consumed_pieces * per
        available = on_hand - reserved_pieces * per
        out[name] = {"unit": item.get("unit", ""), "per_piece": per,
                     "received": received, "on_hand": on_hand,
                     "available": available,
                     "pieces_possible": available // per if per else 0}
    return out, by_order, consumed_pieces, reserved_pieces


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", type=int, help="pieces you want to run; checks feasibility")
    args = ap.parse_args()

    pos, orders, consumed, reserved = position()

    print("Work orders")
    for code, n, st in sorted(orders):
        tag = "consumes" if st in CONSUMED_STATUSES else "reserves" if st in RESERVED_STATUSES else "ignored"
        print(f"   {code:<16}{n:>4} pieces   status={st:<16}({tag})")
    print(f"   {'':<16}{consumed:>4} pieces posted, {reserved} reserved\n")

    print(f"{'item':<26}{'recv':>6}{'on hand':>9}{'avail':>8}{'per pc':>8}{'pieces left':>13}")
    print("-" * 70)
    for name, v in pos.items():
        print(f"{name:<26}{v['received']:>6}{v['on_hand']:>9}{v['available']:>8}"
              f"{v['per_piece']:>8}{v['pieces_possible']:>13}")

    binding = min(pos.items(), key=lambda kv: kv[1]["pieces_possible"])
    print(f"\nBINDING ITEM: {binding[0]} — {binding[1]['pieces_possible']} more piece(s) possible")

    if args.plan:
        short = {n: args.plan * v["per_piece"] - v["available"]
                 for n, v in pos.items() if args.plan * v["per_piece"] > v["available"]}
        if short:
            print(f"\n✗ CANNOT run {args.plan} pieces — short:")
            for n, s in short.items():
                print(f"    {n}: need {args.plan * pos[n]['per_piece']}, "
                      f"have {pos[n]['available']} (short {s})")
            raise SystemExit(1)
        print(f"\n✓ {args.plan} pieces is within stock.")
        for n, v in pos.items():
            print(f"    {n}: {v['available']} → {v['available'] - args.plan * v['per_piece']} after")


if __name__ == "__main__":
    main()
