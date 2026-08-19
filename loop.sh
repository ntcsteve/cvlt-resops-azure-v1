#!/bin/zsh
# ---------------------------------------------------------------------------
# The ResOps loop, one pass. Run it twice, untouched, and the write lane is
# repeatable by someone who is not the person who wrote it. Until then it isn't.
#
#   ./loop.sh infra/workloads pass1
#   ./loop.sh infra/workloads pass2
#
# WHY A SCRIPT AND NOT A CHECKLIST. A checklist executed by the author is still
# the author improvising, quietly, in the gaps. A script cannot improvise.
#
# WHY IT IS THIS DUMB. It echoes, runs, checks the exit code, and stops. No
# retries, no fallbacks, no recovery logic. Every bug found on 2026-08-12 was a
# value that did not mean what its channel implied, so the last thing this needs
# is more machinery deciding things on your behalf. If a step fails, it stops at
# that step and names it. You decide what happens next.
#
# EVERY STEP DECLARES ITS EXPECTED EXIT CODE, and three of them expect non-zero.
# Those three are the workshop. `threatscan` exiting 1 means the scan worked and
# the recovery point is poisoned. `gate` exiting 1 means the ladder refused to
# promote it. If either ever exits 0 on the dirty pass, this run has failed in
# the way that matters most, and the script halts rather than sailing on.
#
# ---------------------------------------------------------------------------
# READ THIS BEFORE THE FIRST PASS
#
# Step 1 is `remediate`, and it is not decoration. The loop's third step takes a
# backup it labels CLEAN, and that label has to be TRUE or every downstream
# verdict is theater. A workload left dirty by a previous session – which is the
# normal state to find one in, and exactly how aug12-narwhal was found on
# 2026-08-12 – would be backed up and called clean.
#
# remediate is safe on an already-clean workload: it is `rm -f` of things that
# may not exist plus a `cp` back from the stash, and it ends by running
# verify.sh and RAISING unless the verdict starts "OK:". So it is also the
# cheapest possible answer to "what state is this thing actually in".
#
# THE ORDER OF THE LAST FOUR STEPS IS FORCED, NOT STYLISTIC.
#
# _attest() in state.py asks the attesters strongest-first, and A NEGATIVE
# ALWAYS WINS:
#
#   Client/Anomaly reports malware  ->  Scan blocks, and the restore drill's
#                                       verdict is never even consulted
#   Client/Anomaly reports 0/absent ->  falls through to the restore-verify
#                                       attestation, which must then COVER the
#                                       newest recovery point
#
# Which forces two things:
#
#   1. The SECOND threatscan is mandatory. The anomaly is a per-CLIENT record,
#      not a per-recovery-point one. Cleaning the VM does not clear it; only a
#      fresh scan overwrites it. Skip step 12 and the gate HOLDs forever no
#      matter how clean the drill comes back.
#
#   2. restore must be the LAST thing that touches recovery points. Its
#      attestation must be NEWER than the newest backup. Any backup after the
#      drill re-breaks coverage. Measured live on 2026-08-12: an attestation
#      written 28 min before the newest backup, correctly refused.
#
# WHAT TO EXPECT, measured across the two passes actually run on 2026-08-12:
#
#   backup           88 to 149 seconds wall clock over the 6 runs in these two
#                    passes. On the tenant side, 17 completed parent jobs measured
#                    77-134s with a median of 91s, plus one 27-minute media agent
#                    failover. PLAN FOR 2 MINUTES.
#
#                    WHY TWO EARLIER FIGURES WERE WRONG, and it is the same cause
#                    both times. A VSA backup produces TWO jobs, both reading as
#                    "Backup": the PARENT (VM Admin Job(Backup)), whose id
#                    POST v4/vmgroup/{id}/backup returns and which poll_job
#                    therefore polls, and a faster CHILD whose id is what the
#                    Azure GXMD snapshot NAME embeds. Sampling snapshot names
#                    measures the child and understates the wait by ~30s a job.
#                    That produced "0.8 min median / 1.4 max", which FIVE OF SIX
#                    real backups then exceeded, and "under 90s in 16 of 16",
#                    which only 8 of 17 parent jobs actually satisfy. Neither
#                    figure was invented; both were measured on the wrong job.
#   threat analysis  3.0 min typical, one 5.7 min outlier in 4
#   restore job      1.4-1.6 min in 5 of 6, ONE at 3.5, from the jobs' own
#                    start/end times. Plus VM boot + verify + teardown around it,
#                    so budget ~4 min wall clock and do not be surprised by 6.
#   one pass         ~20 min       two passes  ~40 min
#
# Every number above is from a run that completed. Timings quoted from memory or
# from a sample that predates a change have been wrong here twice.
#
# THE TWO RISKS, both vendor-side:
#
#   media agent queue   ~1 job in 13 today. poll_job prints the measured range on
#                       its first Waiting tick (do not re-quote it here; it has
#                       been corrected twice and every copy went stale with it),
#                       and every timeout now allows 900s, so it should be a wait
#                       and not a failure. If a step still times out, RE-RUN THAT
#                       STEP ALONE. Do not restart the pass. It is a queue, not a
#                       bug, and restarting costs 25 minutes to learn nothing.
#
#   scheduled backup    the protection plan carries a 1440-min RPO schedule
#                       (task 698975, token-gated so its next run time is not
#                       readable). Zero fired in the six hours of 2026-08-12. If
#                       the final gate HOLDs on COVERAGE rather than promoting,
#                       look for a backup you did not trigger BEFORE suspecting
#                       the code.
# ---------------------------------------------------------------------------
set -u
RUN_DIR=${1:-infra/workloads}
LABEL=${2:-pass1}
LOG="evidence/loop-$LABEL.log"
STEP=0

say()   { print -r -- "\n=========== [$LABEL] $* ===========" | tee -a "$LOG" }
stamp() { date '+%H:%M:%S' }

# run <expected-exit> <description> <cmd...>
run() {
  local want=$1; shift
  local what=$1; shift
  STEP=$((STEP+1))
  say "step $STEP  $what   (expect exit $want)  $(stamp)"
  # STDIN IS CLOSED FOR EVERY STEP, and that is the point of the script. The
  # restore drill pauses on `input()` when sys.stdin.isatty(), so run from a
  # terminal step 13 stops and waits for a keypress: a script that "cannot
  # improvise" sitting there while a human decides something. The pause is right
  # for a person running `op restore` by hand and wrong here, and </dev/null is
  # how you say "nobody is watching" without changing the drill.
  "$@" < /dev/null 2>&1 | tee -a "$LOG"
  local got=${pipestatus[1]}      # zsh: lowercase, and [1] is the command not tee
  if [[ $got -ne $want ]]; then
    print -r -- "\n>>> STOP at step $STEP ($what): exit $got, expected $want" | tee -a "$LOG"
    print -r -- ">>> nothing after this ran. log: $LOG" | tee -a "$LOG"
    exit 1
  fi
  print -r -- "    ok (exit $got)  $(stamp)" | tee -a "$LOG"
}

mkdir -p evidence
print -r -- "loop $LABEL started $(date)" > "$LOG"
OP="python3 -m resops.operator.op"

run 0 "preflight            read-only gate"                    ${=OP} preflight  "$RUN_DIR"
run 0 "remediate            establish a KNOWN-CLEAN baseline"  ${=OP} remediate  "$RUN_DIR"
run 0 "protect              idempotent, reuses the group"      ${=OP} protect    "$RUN_DIR"
run 0 "backup   CLEAN       a trustworthy point exists"        ${=OP} backup     "$RUN_DIR"
run 0 "incident             plant EICAR + .locked"             ${=OP} incident   "$RUN_DIR"
run 0 "backup   DIRTY       the poisoned point"                ${=OP} backup     "$RUN_DIR"
run 1 "threatscan DIRTY     MUST exit 1 - threats found"       ${=OP} threatscan "$RUN_DIR"
run 0 "status               read it: blocked at Scan"          ${=OP} status     "$RUN_DIR"
run 1 "gate     HOLD        MUST refuse to promote"            ${=OP} gate       "$RUN_DIR"
run 0 "remediate            undo the incident, re-verify"      ${=OP} remediate  "$RUN_DIR"
run 0 "backup   CLEAN again a clean newest point"              ${=OP} backup     "$RUN_DIR"
run 0 "threatscan CLEAN     clears the client anomaly"         ${=OP} threatscan "$RUN_DIR"
run 0 "restore              the drill writes the attestation"  ${=OP} restore    "$RUN_DIR"
run 0 "gate     PROMOTE     MUST promote"                      ${=OP} gate       "$RUN_DIR"

say "PASS COMPLETE - 14 steps, every exit code as expected   $(stamp)"
print -r -- "log: $LOG"
print -r -- "the workload is CLEAN and PROMOTED. pass 2 can start immediately."
