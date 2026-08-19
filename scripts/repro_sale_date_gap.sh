#!/usr/bin/env bash
# Repro for [SALE-DATE-WRITE-STOPPED]: sale_date unwritten on sold docs since ~Feb 2026.
# Expected: the "since 2026-05-01" column is 0 for all three suburbs, while
# PropRadar independently records 106 sales across them in May 2026 alone.
set -euo pipefail
cd /home/fields/Fields_Orchestrator
# shellcheck disable=SC1091
source /home/fields/venv/bin/activate
set -a; source /home/fields/Fields_Orchestrator/.env; set +a
python3 - <<'PY'
from shared.db import get_gold_coast_db
db = get_gold_coast_db()
print(f"{'collection':18} {'sold':>6} {'has sale_date':>14} {'>=2026-02-01':>13} {'>=2026-05-01':>13}")
for c in ("robina", "varsity_lakes", "burleigh_waters"):
    q = {"listing_status": "sold"}
    print(f"{c:18} "
          f"{db[c].count_documents(q):>6} "
          f"{db[c].count_documents({**q, 'sale_date': {'$exists': True, '$ne': None}}):>14} "
          f"{db[c].count_documents({**q, 'sale_date': {'$gte': '2026-02-01'}}):>13} "
          f"{db[c].count_documents({**q, 'sale_date': {'$gte': '2026-05-01'}}):>13}")
PY
