#!/usr/bin/env python3
"""
mail_log.py — the durable record of every physical mail piece we have sent.

ONE doc per (order, address) in system_monitor.mail_log. This is the source of
truth for "which addresses have we mailed, exactly what did each receive, and when
was it posted" — it survives the 60-day organic_journeys rollover and does not
depend on the stock ledger or a Drive manifest staying around.

    _id            "<order_number>:<slug>"   (idempotent upsert key)
    slug, address, suburb
    order_number   PD-000N
    flow_code      e.g. Fields_OTN.1
    ab_arm         "with_letter" | "no_letter" | null
    contents       [{component, qty}, ...]   what physically went in the envelope
    contents_str   human one-liner
    envelope       "C4 branded"
    batch_date     YYYY-MM-DD (staged/dispatched)
    drive_folder   Pronto Drive sub-folder name
    posted_date    null until John confirms lodged with Australia Post
    posted_source  who/what confirmed it
    lead_source, lead_date          (provenance, where known)
    posthog_distinct_id, crm_contact_id   (join keys, filled opportunistically)
    created_at, updated_at

Why it exists: before this, "already mailed" lived only in fulfilment_work_orders
(PD-0001 only — PD-0002 was never recorded) plus a Drive manifest.csv. A DB-only
exclusion query silently re-mailed the 50 PD-0002 recipients. mail_log is the one
place every batch writes to, so the next selection can exclude reliably.

CLI:
  python3 scripts/mail_log.py backfill-workorders
  python3 scripts/mail_log.py backfill-manifest --manifest X.csv --order PD-0002 \
      --flow Fields_OT.1 --arm with_letter --contents "owner_teaser:1,hand_written_note:1,fridge_magnet:2" \
      --batch-date 2026-08-26 --drive-folder "Fields_OT.1_2026-08-26_PD-0002"
  python3 scripts/mail_log.py export --out fulfilment/MAIL_LOG.csv
  python3 scripts/mail_log.py set-posted --order PD-0003 --date 2026-09-05 --source "John email"
  python3 scripts/mail_log.py mailed-slugs          # print every already-mailed slug
"""
from __future__ import annotations
import argparse, ast, csv, datetime as dt, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from shared.db import get_client  # noqa: E402

SUBURBS = {"robina": "Robina", "varsity-lakes": "Varsity Lakes",
           "burleigh-waters": "Burleigh Waters"}


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _suburb(slug: str, address: str | None) -> str:
    for suf, name in SUBURBS.items():
        if slug.endswith(suf):
            return name
    return (address or "").split(",")[-1].strip() if address else ""


def _parse_contents(spec: str):
    """'owner_teaser:1,fridge_magnet:2' -> [{'component':..,'qty':..}, ...]"""
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        comp, _, qty = part.partition(":")
        out.append({"component": comp.strip(), "qty": int(qty or 1)})
    return out


def _contents_str(contents):
    return " + ".join(f"{c['component']}×{c['qty']}" for c in contents)


def col():
    return get_client()["system_monitor"]["mail_log"]


def record(order_number, flow_code, arm, contents, envelope, batch_date, drive_folder,
           slug, address, lead_source=None, lead_date=None,
           posthog_distinct_id=None, crm_contact_id=None):
    now = _now()
    doc = {
        "slug": slug, "address": address, "suburb": _suburb(slug, address),
        "order_number": order_number, "flow_code": flow_code, "ab_arm": arm,
        "contents": contents, "contents_str": _contents_str(contents),
        "envelope": envelope, "batch_date": batch_date, "drive_folder": drive_folder,
        "lead_source": lead_source, "lead_date": lead_date,
        "posthog_distinct_id": posthog_distinct_id, "crm_contact_id": crm_contact_id,
        "updated_at": now,
    }
    col().update_one(
        {"_id": f"{order_number}:{slug}"},
        {"$set": doc,
         "$setOnInsert": {"created_at": now, "posted_date": None, "posted_source": None}},
        upsert=True)
    return f"{order_number}:{slug}"


def backfill_workorders():
    """PD-0001 = the two mailer_v2 work orders (Fields_01.1 + Fields_02.1)."""
    db = get_client()["system_monitor"]
    contents = [{"component": "mailer_v2", "qty": 1}, {"component": "fridge_magnet", "qty": 2}]
    n = 0
    for wo in db["fulfilment_work_orders"].find({}):
        items = wo.get("items")
        items = ast.literal_eval(items) if isinstance(items, str) else (items or [])
        flow = wo.get("flow_code")
        folder = wo.get("drive_folder") or "2026-08-17_Fields_01.1_and_02.1_PD-0001"
        d = wo.get("dispatched_at")
        bdate = (d.date().isoformat() if isinstance(d, dt.datetime)
                 else str(d)[:10] if d else "2026-08-17")
        for it in items:
            record("PD-0001", flow, None, contents, "C4 branded", bdate, folder,
                   it["slug"], it.get("address"),
                   lead_source=it.get("lead_source"), lead_date=it.get("lead_date"))
            n += 1
    return n


def backfill_manifest(path, order, flow, arm, contents, envelope, batch_date, drive_folder):
    n = 0
    with open(path) as fh:
        for row in csv.DictReader(fh):
            slug = (row.get("slug") or "").strip()
            if not slug:
                continue
            record(order, flow, arm, contents, envelope, batch_date, drive_folder,
                   slug, (row.get("address") or "").strip())
            n += 1
    return n


def export_csv(out):
    rows = list(col().find({}).sort([("order_number", 1), ("slug", 1)]))
    fields = ["order_number", "slug", "address", "suburb", "flow_code", "ab_arm",
              "contents_str", "envelope", "batch_date", "drive_folder",
              "posted_date", "posted_source", "lead_source", "lead_date"]
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})
    return len(rows)


def set_posted(order, date, source):
    res = col().update_many(
        {"order_number": order},
        {"$set": {"posted_date": date, "posted_source": source, "updated_at": _now()}})
    return res.modified_count


def mailed_slugs():
    return sorted({d["slug"] for d in col().find({}, {"slug": 1})})


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("backfill-workorders")
    m = sub.add_parser("backfill-manifest")
    m.add_argument("--manifest", required=True); m.add_argument("--order", required=True)
    m.add_argument("--flow", required=True); m.add_argument("--arm", default=None)
    m.add_argument("--contents", required=True); m.add_argument("--envelope", default="C4 branded")
    m.add_argument("--batch-date", required=True); m.add_argument("--drive-folder", required=True)
    e = sub.add_parser("export"); e.add_argument("--out", default="fulfilment/MAIL_LOG.csv")
    p = sub.add_parser("set-posted")
    p.add_argument("--order", required=True); p.add_argument("--date", required=True)
    p.add_argument("--source", default="John confirmation")
    sub.add_parser("mailed-slugs")
    args = ap.parse_args()

    if args.cmd == "backfill-workorders":
        print("recorded", backfill_workorders(), "PD-0001 pieces")
    elif args.cmd == "backfill-manifest":
        n = backfill_manifest(args.manifest, args.order, args.flow, args.arm,
                              _parse_contents(args.contents), args.envelope,
                              args.batch_date, args.drive_folder)
        print("recorded", n, f"{args.order} pieces")
    elif args.cmd == "export":
        print("wrote", export_csv(args.out), "rows ->", args.out)
    elif args.cmd == "set-posted":
        print("marked posted:", set_posted(args.order, args.date, args.source), "pieces")
    elif args.cmd == "mailed-slugs":
        for s in mailed_slugs():
            print(s)


if __name__ == "__main__":
    main()
