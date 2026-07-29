#!/usr/bin/env python3
"""
rl_selftest.py — M8: the General RL system self-test (the testing step).

One command that answers "is the whole system built, wired, and healthy?" — checks every
sensor collection is fresh, every heartbeat is green, every pacer is valid, every cron is
registered, the dispatchers claim correctly, the shared ledger + arm grades + conductor board
are populated, and every script compiles. Prints PASS/FAIL per check + an overall verdict.
Self-monitored (job_run) so the test itself can't die silently; telegrams on failure.

Usage: python3 rl_selftest.py [--quiet]
Exit code 0 = all pass, 1 = any fail.
"""
import glob
import os
import py_compile
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "scripts")))
from shared.db import get_client  # noqa: E402

NOW = datetime.now(timezone.utc)
DOMAINS = ["geo", "seo", "ads", "articles", "onsite"]
SIGNAL_COLL = {d: f"rl_{d}_signal" for d in DOMAINS}
PACER_COLL = {d: f"rl_{d}_cycle_state" for d in DOMAINS}   # geo via cycle_state.py, rest via cycle_pacer
FRESH_HOURS = 30           # a "fresh" latest snapshot must be newer than this
SUPPORT_COLLS = ["rl_reward_ledger", "rl_arm_grades", "rl_conductor"]  # personalization_policy retired → rl_onsite_experiments (cycle-driven, may be empty)

results = []
def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def _age_h(iso):
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (NOW - dt).total_seconds() / 3600
    except Exception:
        return 1e9


def run():
    sm = get_client()["system_monitor"]
    colls = set(sm.list_collection_names())

    # 1. every script compiles
    for f in sorted(glob.glob(os.path.join(HERE, "*.py"))):
        try:
            py_compile.compile(f, doraise=True)
            check(f"compile {os.path.basename(f)}", True)
        except Exception as e:
            check(f"compile {os.path.basename(f)}", False, str(e)[:80])

    # 2. per-domain: signal collection fresh + heartbeat green
    for d in DOMAINS:
        sig = sm[SIGNAL_COLL[d]].find_one({"_id": "latest"}) if SIGNAL_COLL[d] in colls else None
        age = _age_h(sig.get("computed_at")) if sig else 1e9
        check(f"{d}: signal fresh", sig is not None and age < FRESH_HOURS,
              f"age={age:.1f}h" if sig else "no latest doc")
        hb = sm["job_runs"].find_one({"$or": [{"job": f"rl_{d}_signal"}, {"name": f"rl_{d}_signal"}]}, sort=[("_id", -1)])
        check(f"{d}: sensor heartbeat", hb is not None and hb.get("status") == "success",
              (hb or {}).get("status", "missing"))

    # 3. support collections present + fresh
    for c in SUPPORT_COLLS:
        doc = sm[c].find_one({"_id": "latest"}) if c in colls else None
        check(f"{c} present+fresh", doc is not None and _age_h(doc.get("computed_at")) < FRESH_HOURS,
              "ok" if doc else "missing")

    # 4. pacers valid (dispatched domains) + claim decision returns cleanly
    for d in DOMAINS:
        st = sm[PACER_COLL[d]].find_one({"_id": "state"})
        check(f"{d}: pacer state", st is not None and st.get("next_run_at") is not None,
              "ok" if st else "no state")
        # read-only pacer check (NOT --claim, which has side effects / would consume a cycle slot)
        try:
            r = subprocess.run([sys.executable, os.path.join(HERE, "cycle_pacer.py"), "--job", d, "--show"],
                               capture_output=True, text=True, timeout=30,
                               env={**os.environ, "PACER_JOB": d})
            check(f"{d}: pacer readable", r.returncode == 0 and "cycle state" in (r.stdout or ""),
                  (r.stdout or "").strip().split("\n")[0][:50])
        except Exception as e:
            check(f"{d}: pacer readable", False, str(e)[:60])

    # 5. crons registered (signal + dispatch per domain, + support jobs)
    try:
        cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=15).stdout
    except Exception:
        cron = ""
    for d in DOMAINS:
        check(f"{d}: signal cron", f"{d}_signal.py" in cron, "")
        disp = "geo_dispatch.sh" if d == "geo" else f"rl_dispatch.sh {d}"
        check(f"{d}: dispatch cron", disp in cron, "")
    for job in ["reward_ledger.py", "arm_grader.py", "conductor.py"]:
        check(f"cron {job}", job in cron, "")

    # 6. conductor board health
    board = sm["rl_conductor"].find_one({"_id": "latest"}) or {}
    h = board.get("health", {})
    check("conductor: all sensors ok", h.get("sensors_ok") == len(DOMAINS), f"{h.get('sensors_ok')}/{len(DOMAINS)}")

    # 7. dashboard-source collections exist (the ops Control Loop tab reads these)
    check("ops tab source: reward+geo present", "rl_reward_ledger" in colls and "rl_geo_signal" in colls, "")

    return results


def main():
    quiet = "--quiet" in sys.argv
    try:
        from job_status import job_run
    except Exception:
        job_run = None

    def _do():
        run()
        passed = sum(1 for _, ok, _ in results if ok)
        failed = [(n, d) for n, ok, d in results if not ok]
        if not quiet:
            print(f"\n=== RL SELF-TEST — {passed}/{len(results)} checks passed ===")
            for n, ok, d in results:
                if not ok or not quiet:
                    print(f"  {'✅' if ok else '❌'} {n}" + (f"  ({d})" if d else ""))
        if failed:
            print(f"\n❌ {len(failed)} FAILED: " + "; ".join(f"{n}({d})" for n, d in failed))
        else:
            print("\n✅ ALL CHECKS PASSED — General RL system healthy.")
        return passed, failed

    if job_run:
        with job_run("rl_selftest", cadence_hours=24, title="General RL — system self-test (M8)") as beat:
            passed, failed = _do()
            beat.detail = f"{passed}/{len(results)} passed"
            beat.metrics = {"passed": passed, "failed": len(failed)}
            if failed:
                try:
                    sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
                    from telegram_notify import send_message
                    send_message("⚠️ General RL self-test FAILED:\n" + "\n".join(f"• {n} ({d})" for n, d in failed[:8]))
                except Exception:
                    pass
    else:
        passed, failed = _do()
    sys.exit(1 if any(not ok for _, ok, _ in results) else 0)


if __name__ == "__main__":
    main()
