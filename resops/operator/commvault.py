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
            print("         (waiting for a media agent slot — normal on first run, typically 5–15 min)",
                  flush=True)
            first_wait = False
        if any(t in status for t in TERMINAL):
            return status
        time.sleep(every)
        waited += every
    return "TIMEOUT"
