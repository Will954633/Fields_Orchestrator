#!/usr/bin/env bash
# weekly_cycle.sh <domain> — fixed-cadence runner for a General RL domain.
#
# REPLACES rl_cycle.sh + rl_dispatch.sh + cycle_pacer.py. Those implemented SELF-PACING:
# each domain chose its own next wake, was allowed 14 runs/day, and every prompt ended
# "CHAIN 20-45 min if actionable work in hand". Six domains doing that produced 27 cycles
# and 31 human-decision items in 48 hours, and Will paused the whole fleet on 2026-07-30.
#
# The pacer solved a problem we do not have (spending compute efficiently) and created the
# one we do (unbounded demand on Will's attention). So: no pacer, no chaining, no claim
# protocol. Cron says when. Once a week. That is the entire scheduling policy.
#
# Manual run: bash weekly_cycle.sh seo
set -uo pipefail
DOMAIN="${1:?usage: weekly_cycle.sh <domain>}"
DIR=/home/fields/Fields_Orchestrator/16_General_Reinforcement_Learning
LOG="/home/fields/Fields_Orchestrator/logs/rl_weekly_${DOMAIN}.log"
LOCK="/tmp/rl_weekly_${DOMAIN}.lock"
PROMPT_FILE="$DIR/${DOMAIN}_prompt.md"
SENSOR="$DIR/${DOMAIN}_signal.py"
STAMP=$(TZ=Australia/Brisbane date +%Y%m%d_%H%M)
MODEL="${RL_MODEL:-claude-opus-5}"
# 40 min. The old runner allowed 25 (domains) / 60 (conductor); weekly cycles do more per
# run than daily ones did, but an agent that needs longer than this is thrashing, not working.
BUDGET_SEC="${RL_BUDGET_SEC:-2400}"

[ -f "$PROMPT_FILE" ] || { echo "[$STAMP] no prompt $PROMPT_FILE" >> "$LOG"; exit 1; }

exec 9>"$LOCK"
if ! flock -n 9; then echo "[$STAMP] previous $DOMAIN cycle still running — skip" >> "$LOG"; exit 0; fi

cd /home/fields/Fields_Orchestrator
set -a; source ./.env; set +a
source /home/fields/venv/bin/activate 2>/dev/null || true
export GH_CONFIG_DIR=/home/projects/.config/gh
export CYCLE_STAMP="$STAMP"
export CYCLE_WEEK=$(TZ=Australia/Brisbane date +%G-W%V)
export CYCLE_DIR="$DIR/cycles/$CYCLE_WEEK/$(TZ=Australia/Brisbane date +%Y-%m-%d)"
export CYCLE_START_EPOCH=$(date +%s)
export RL_DOMAIN="$DOMAIN"
mkdir -p "$CYCLE_DIR"
unset CLAUDECODE CLAUDE_CODE_SSE_PORT 2>/dev/null || true
unset ANTHROPIC_API_KEY 2>/dev/null || true   # force Claude Max, never metered API billing

echo "[$STAMP] ===== $DOMAIN weekly cycle start (model=$MODEL) =====" >> "$LOG"

# Sensor first, so the agent reasons over current data rather than last week's snapshot.
# A stale `latest` doc is indistinguishable from a fresh one to the agent — under the old
# system every domain read a 2-week-old ledger without noticing.
SIG_RC=0
if [ -f "$SENSOR" ]; then
  python3 "$SENSOR" >> "$LOG" 2>&1; SIG_RC=$?
  echo "[$STAMP] ${DOMAIN}_signal rc=$SIG_RC" >> "$LOG"
else
  echo "[$STAMP] no sensor $SENSOR — skipping refresh" >> "$LOG"
fi

# Extra sensors some domains need beyond their own. Kept here rather than left to the
# agent to remember: a sensor the prompt merely *asks* for is a sensor that silently stops
# running the week the agent is busy. seo owns the brand SERP (Will, 2026-08-13), and
# brand_serp_signal.py is what turns that from "have a look" into a measured score.
case "$DOMAIN" in
  seo)
    if [ -f "$DIR/brand_serp_signal.py" ]; then
      python3 "$DIR/brand_serp_signal.py" >> "$LOG" 2>&1
      echo "[$STAMP] brand_serp_signal rc=$?" >> "$LOG"
    fi
    ;;
esac

CYCLE_DOC="$CYCLE_DIR/${DOMAIN}_cycle_${STAMP}.md"
RUN_LOG="/tmp/rl_weekly_${DOMAIN}_${STAMP}.out"

# The ops domain gets a tamper baseline, carried over from the retired ops_cycle.sh.
# It exists because the cheapest way to make a health board go green is to silence the
# check rather than fix anything. The ops mandate forbids that — but a guard that relies
# on the guarded party honouring it is not a guard. Snapshot BEFORE the agent runs.
INTEG_SNAP=""
if [ "$DOMAIN" = "ops" ] && [ -f "$DIR/ops_integrity.py" ]; then
  INTEG_SNAP="/tmp/ops_integrity_${STAMP}.json"
  python3 "$DIR/ops_integrity.py" before "$INTEG_SNAP" >> "$LOG" 2>&1
fi

# The shared contract is PREPENDED to the domain mandate rather than copied into each of
# the six prompt files. Written once, it cannot drift per-domain, and the mandates keep
# their hard-won domain knowledge. The contract states that it overrides the mandate where
# the two disagree — the mandates still carry self-pacing/Telegram instructions from the
# old daily system, and those instructions are now wrong.
CONTRACT="$DIR/_CYCLE_CONTRACT.md"
[ -f "$CONTRACT" ] || { echo "[$STAMP] FATAL: missing $CONTRACT" >> "$LOG"; exit 1; }

FULL_PROMPT="$(cat "$CONTRACT")

═══════════════════════════════════════════════════════════════════════════════
YOUR DOMAIN MANDATE ($DOMAIN) — subordinate to the contract above
═══════════════════════════════════════════════════════════════════════════════

$(cat "$PROMPT_FILE")"

# --max-turns was 80 until 2026-08-16, when it silently killed THREE of seven domains in one
# cycle (seo, articles, onsite — all "Error: Reached max turns (80)"; articles had already lost
# one run to it on 08-13). onsite got far enough to raise two recommendations and then died
# before writing its cycle doc, which is the worst shape: findings exist, the reasoning behind
# them does not. There are TWO ceilings on this call and only one of them is meaningful —
# BUDGET_SEC (2400s) bounds real cost; a turn count bounds nothing anyone chose. All three
# failures ran 13-17 minutes, i.e. nowhere near the time budget. 200 lets the wall-clock
# budget be the actual bound, which is the ceiling we actually reasoned about.
#
# Retry once on a transient AUTH failure only — not on any other error.
# On 2026-08-13 the ops cycle died on "OAuth session expired and could not be refreshed"
# at 07:15:25; the identical refresh token then succeeded from another process 110 seconds
# later. Nothing was actually wrong — the access token has an 8h TTL, so the first claude
# invocation of the day is always the one that must refresh, and it gets no second chance.
# A daily job losing that coin-flip costs a day. A WEEKLY job loses seven, which is why
# this retry lives here even though the original incident was on a daily cycle.
AUTH_FAIL=0
TURN_FAIL=0
RC=0
for attempt in 1 2; do
  set +e
  timeout -k 60 "$BUDGET_SEC" claude --model "$MODEL" -p "$FULL_PROMPT" \
    --allowedTools "Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch,TodoWrite" \
    --max-turns 200 > "$RUN_LOG" 2>&1
  RC=$?
  set -e 2>/dev/null || true

  AUTH_FAIL=0
  grep -qF "OAuth session expired" "$RUN_LOG" && AUTH_FAIL=1
  grep -qF "Failed to authenticate" "$RUN_LOG" && AUTH_FAIL=1
  # Name this one specifically. "claude -p rc=1" is the same string for "never authenticated",
  # "crashed" and "ran out of turns", and on 2026-08-16 that ambiguity hid a three-domain
  # outage behind a generic red row for a full cycle.
  grep -qF "Reached max turns" "$RUN_LOG" && TURN_FAIL=1

  cat "$RUN_LOG" >> "$LOG"
  if [ "$AUTH_FAIL" -eq 0 ]; then break; fi
  if [ "$attempt" -eq 1 ]; then
    echo "[$STAMP] auth failure on attempt 1 — sleeping 120s and retrying once" >> "$LOG"
    sleep 120
  else
    echo "[$STAMP] auth failure on attempt 2 — giving up" >> "$LOG"
  fi
done
echo "[$STAMP] ===== $DOMAIN weekly cycle end (rc=$RC auth_fail=$AUTH_FAIL) =====" >> "$LOG"

# ── Rule 7b: assert an OUTCOME, not merely that nothing threw. ─────────────────────
# The zero-output path here is real and has already bitten us: on 2026-08-13 the ops cycle
# died on a transient OAuth refresh failure and wrote nothing. That run's heartbeat DID say
# "error" — the gap was not the status but the DETAIL, which read only "claude -p rc=1",
# byte-identical to the 08-09 run that worked hard and hit its turn limit. You could not
# tell "never started" from "ran out of road". So below we name the specific failure, and
# treat a missing cycle doc as fatal regardless of exit code: a cycle that produced no
# document did not happen. (ops_integrity.py's "clean" is similarly misleading here — it is
# literally true, because a run that never starts touches nothing.)
DOC_OK=0
[ -s "$CYCLE_DOC" ] && DOC_OK=1
rm -f "$RUN_LOG"

# Verify ops fixed rather than silenced. This telegrams Will and records an ERROR heartbeat
# on any violation, so a tampering cycle is LOUDER than a merely failing one. Only run the
# comparison if the agent actually did something — on a cycle that never started it would
# report "clean", which is true but reads as false reassurance.
if [ -n "$INTEG_SNAP" ] && [ -f "$INTEG_SNAP" ]; then
  if [ "$DOC_OK" -eq 1 ]; then
    python3 "$DIR/ops_integrity.py" after "$INTEG_SNAP" >> "$LOG" 2>&1
    echo "[$STAMP] ops_integrity rc=$?" >> "$LOG"
  else
    echo "[$STAMP] ops_integrity: N/A — the agent never produced a cycle doc" >> "$LOG"
  fi
  rm -f "$INTEG_SNAP"
fi

python3 - "$DOMAIN" "$RC" "$DOC_OK" "$AUTH_FAIL" "$SIG_RC" "$CYCLE_DOC" "$TURN_FAIL" <<'PY' 2>/dev/null || true
import sys
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
dom, rc, doc_ok, auth_fail, sig_rc, doc = (
    sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]),
    int(sys.argv[5]), sys.argv[6])
turn_fail = int(sys.argv[7])
try:
    from job_status import record_job_result
    problems = []
    if auth_fail:
        problems.append("Claude Max OAuth failed — the agent never ran")
    if turn_fail:
        problems.append("hit --max-turns — the agent ran out of road mid-cycle, "
                        "it did not fail to start")
    if rc != 0:
        problems.append(f"claude -p rc={rc}")
    if not doc_ok:
        problems.append(f"NO CYCLE DOC written ({doc}) — the cycle produced nothing")
    if sig_rc != 0:
        problems.append(f"sensor rc={sig_rc} (agent reasoned over stale data)")
    status = "error" if problems else "success"
    detail = "; ".join(problems) if problems else f"cycle doc written: {doc}"
    # 168h cadence, 200h stale window: one missed week flags without alarming on a
    # cycle that ran a few hours late.
    record_job_result(f"rl_weekly_{dom}", status,
                      cadence_hours=168, stale_hours=200,
                      title=f"General RL — {dom.upper()} weekly cycle",
                      detail=detail)
    print(f"heartbeat: {status} — {detail}")
except Exception as e:
    print("job_status record failed:", e)
PY
exit 0
