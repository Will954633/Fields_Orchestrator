"""
L — Credential evidence register.

ACL / PO Act: public claims about an agent's experience, skills, qualifications or
licensing must be substantiable (don't exaggerate). This register maps every
public credential claim (chiefly the mini-site "Your Agent" tab) to the evidence
that backs it. The evidence FILES live in Google Drive (Compliance/Credentials/);
this register (system_monitor.credential_register) is the index + verification log.

Statuses:
  verified         — evidence on file (evidence_ref points to it), checked by a person
  evidence_pending — claim is published but the proof doc hasn't been filed yet
  retired          — claim no longer made publicly

Usage:
  python3 -m scripts.compliance.credential_register --seed     # upsert the known claims
  python3 -m scripts.compliance.credential_register --list
  python3 -m scripts.compliance.credential_register --verify <id> --ref "drive:Credentials/x.pdf" --by "Will Simpson"
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from pymongo import MongoClient

from scripts.compliance import LICENCE_NO, LICENSEE_NAME

COLL = "credential_register"

# Current public credential claims. `surface` records where each is asserted so a
# wording change there triggers a re-check here. Licence is verifiable on the QLD
# OFT public register; experience/training claims need Will's documents filed.
SEED = [
    {
        "claim_id": "qld-licence",
        "claim_text": f"Licensed real estate professional — Queensland (Licence No. {LICENCE_NO}).",
        "surface": "YourAgentTab / ReportFooter / AboutPage / EditorialPolicyPage / DisclaimerPage",
        "evidence_type": "licence",
        "evidence_ref": "QLD OFT licensee public register (verifiable online); certificate to be filed in Compliance/Credentials/",
        "status": "verified",
        "verified_by": LICENSEE_NAME,
        "notes": "Number confirmed by the licensee 2026-06-21.",
    },
    {
        "claim_id": "finance-background",
        "claim_text": "Background in financial analysis and fund management.",
        "surface": "YourAgentTab",
        "evidence_type": "employment / qualification",
        "evidence_ref": None,
        "status": "evidence_pending",
        "notes": "File CV / employment records / qualifications in Compliance/Credentials/, then --verify.",
    },
    {
        "claim_id": "negotiation-training",
        "claim_text": "Negotiation training (shapes how a sale is run once the campaign begins).",
        "surface": "YourAgentTab",
        "evidence_type": "training certificate",
        "evidence_ref": None,
        "status": "evidence_pending",
        "notes": "File the course certificate in Compliance/Credentials/, then --verify.",
    },
    {
        "claim_id": "published-accuracy",
        "claim_text": "Proprietary comparable-sales valuation model with published accuracy benchmarks.",
        "surface": "AboutPage / ValuationTab",
        "evidence_type": "backtest record",
        "evidence_ref": "system_monitor.valuation_accuracy (weekly backtest log)",
        "status": "verified",
        "verified_by": LICENSEE_NAME,
        "notes": "Backed by the weekly backtest; do NOT pair with competitor-superiority claims (see valuation_backtest_claim_constraints).",
    },
]


def _coll():
    conn = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn:
        sys.exit("COSMOS_CONNECTION_STRING not set")
    return MongoClient(conn)["system_monitor"][COLL]


def seed() -> None:
    coll = _coll()
    coll.create_index("claim_id", unique=True)
    now = datetime.utcnow()
    for c in SEED:
        existing = coll.find_one({"claim_id": c["claim_id"]})
        if existing:
            # Refresh wording/surface but PRESERVE a human's verification.
            update = {"claim_text": c["claim_text"], "surface": c["surface"],
                      "evidence_type": c["evidence_type"], "updated_at": now}
            coll.update_one({"claim_id": c["claim_id"]}, {"$set": update})
            print(f"  updated   {c['claim_id']} ({existing.get('status')})")
        else:
            doc = {**c, "created_at": now, "updated_at": now}
            doc.setdefault("verified_at", now if c.get("status") == "verified" else None)
            coll.insert_one(doc)
            print(f"  seeded    {c['claim_id']} [{c['status']}]")


def verify(claim_id: str, ref: str, by: str) -> None:
    coll = _coll()
    now = datetime.utcnow()
    res = coll.update_one(
        {"claim_id": claim_id},
        {"$set": {"status": "verified", "evidence_ref": ref, "verified_by": by,
                  "verified_at": now, "updated_at": now}})
    print("verified" if res.modified_count else "no such claim_id", claim_id)


def list_all() -> None:
    coll = _coll()
    print(f"{'claim_id':22} {'status':17} {'evidence_ref'}")
    for c in coll.find(sort=[("claim_id", 1)]):
        print(f"{c['claim_id']:22} {c['status']:17} {c.get('evidence_ref') or '— (pending)'}")
    pend = coll.count_documents({"status": "evidence_pending"})
    if pend:
        print(f"\n⚠️  {pend} claim(s) need evidence filed in Drive Compliance/Credentials/ then --verify.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Credential evidence register (compliance item L)")
    ap.add_argument("--seed", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--verify", metavar="CLAIM_ID")
    ap.add_argument("--ref")
    ap.add_argument("--by", default=LICENSEE_NAME)
    args = ap.parse_args()
    if args.verify:
        if not args.ref:
            sys.exit("--verify requires --ref")
        verify(args.verify, args.ref, args.by)
    elif args.list:
        list_all()
    else:
        seed()
        print()
        list_all()


if __name__ == "__main__":
    main()
