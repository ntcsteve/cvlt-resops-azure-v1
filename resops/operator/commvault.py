"""
Commvault job polling — the ONE poll loop, shared by the operator backup and the
restore drill so the terminal states and cadence can't drift between lanes.
"""
from __future__ import annotations

import time

TERMINAL = ("Completed", "Failed", "Killed")


def job_summary(client, job_id) -> dict:
    """A job's summary block. Callers need more than the status string: a job can
    report "Completed" having processed nothing at all, and the difference only
    shows up in totalNumOfFiles / sizeOfApplication."""
    return (client.get(f"Job/{job_id}").json().get("jobs") or [{}])[0].get("jobSummary", {})


def poll_job(client, job_id, timeout: int = 600, every: int = 20) -> str:
    """Poll a Commvault job to a terminal state. Prints progress each tick; returns
    the final status string (or "TIMEOUT"). `client` is the read-only resops Client
    (a GET-only poll — the mutating trigger already happened)."""
    print(f"polling job {job_id} (terminal = {'/'.join(TERMINAL)})…")
    waited = 0
    first_wait = True
    while waited <= timeout:
        summary = (client.get(f"Job/{job_id}").json().get("jobs") or [{}])[0].get("jobSummary", {})
        status = summary.get("status", "")
        pending = summary.get("pendingReason", "").strip()
        reason = f"  ↳ {pending}" if pending and status == "Waiting" else ""
        print(f"  [{waited:4}s] {status} {summary.get('percentComplete')}%{reason}", flush=True)
        if status == "Waiting" and first_wait:
            # THE ORIGIN OF A NUMBER NOBODY MEASURED, twice over. This first said
            # "typically 5-15 min" (invented), then "under 90s in 16 of 16 jobs"
            # (measured, but on the wrong jobs). loop.sh, FACILITATOR.md and
            # WORKSHOP.md all quote whatever this says, so a wrong figure here
            # reseeds every copy.
            #
            # WHY THE SECOND ATTEMPT WAS WRONG, and it is the eleventh instance of
            # this repo's one recurring bug. A VSA backup produces TWO jobs:
            #
            #   VM Admin Job(Backup)   the PARENT. This is the id
            #                          POST v4/vmgroup/{id}/backup returns, so it
            #                          is the one this function polls and the one
            #                          a participant waits for.
            #   Backup                 the CHILD. Faster, and its id is what the
            #                          Azure GXMD snapshot NAME embeds.
            #
            # Both read as "Backup". Sampling the snapshot names therefore measures
            # the child and understates the wait by roughly 30 seconds a job. That
            # is where "0.8 min median" came from, and why the next session found
            # five of six real backups exceeding a stated maximum.
            #
            # RE-MEASURED 2026-08-18 on the PARENT jobs this function actually
            # polls: 17 completed, 77s to 134s, median 91s, plus one 27-minute
            # media agent failover. Only 8 of 17 were under 90 seconds. Wall clock
            # for `op backup` end to end, from loop.sh's own step stamps: 88s to
            # 149s across 6 runs.
            print("         (waiting for a media agent slot — measured here: about 2 min, "
                  "77-149s across 23 runs, and one media agent failover took 27 min. "
                  "Do not kill it.)",
                  flush=True)
            first_wait = False
        if any(t in status for t in TERMINAL):
            return status
        time.sleep(every)
        waited += every
    return "TIMEOUT"


def succeeded(status: str) -> bool:
    """Did the job reach a terminal state that produced what we asked for?

    THIS EXISTS BECAUSE "TIMEOUT" IS NOT A JOB STATUS. poll_job returns it when
    it stopped waiting, which means the job may still be running and we never saw
    an outcome. We cannot claim a result we did not observe, so it is a failure —
    and it lives in the same return channel as real statuses, so every reader had
    to remember to special-case it by hand. One reader did (the restore drill,
    with a three-way string match) and one did not (backup, which returned it and
    exited 0). Deciding this in one place is the whole point.

    "Completed w/ one or more warnings" and "…errors" both contain "Completed"
    and count as success HERE, because the job produced data. Whether that data
    is any good is judged elsewhere and independently: the Detect rung reads the
    group's own lastBackup status, and verify.sh opens the restored copy and
    looks. This function judges the JOB and nothing else.
    """
    return "Completed" in (status or "")
