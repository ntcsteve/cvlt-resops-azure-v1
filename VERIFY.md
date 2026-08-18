# `verify.sh` — the recovery contract

> **This is the one file you have to write yourself, and the one nobody can write for you.**

> Lost? [README.md](README.md) runs the toolkit · [RESOPS.md](RESOPS.md) is the idea · [WORKSHOP.md](WORKSHOP.md) is the facilitated day.

A backup product can tell you a job completed. Only your workload can tell you whether what came back is the thing you needed. `verify.sh` is that answer, expressed as a script, run **inside the restored copy** by a drill that opened the recovery point in isolation.

It is the test. The drill is the test runner. `resops gate` is the required check.

## The contract

```
 WHERE     /opt/app/verify.sh inside the workload, executable (chmod +x)
 WHEN      the restore drill runs it in the RESTORED copy, never the live one
 OUTPUT    exactly one verdict line on stdout:
               OK:   <what you proved>
               FAIL: <what was wrong>
 EXIT      0 on OK, non-zero on FAIL
 RESULT    evidence/attestations/<workload>.json, read by the Scan rung
```

Four rules, and every one of them exists because breaking it produces a *silent* wrong answer rather than an error.

**1. The verdict line is authoritative, not the exit code.** The drill reads the first line starting with `OK:` or `FAIL:`. Make the exit code agree with it anyway, but understand which one is parsed.

**2. Keep each verdict message on ONE line.** The parser takes the first matching line and stops. A wrapped message is silently truncated mid-sentence into the attestation, the gate reason and the evidence bundle. This has already happened once in this repo.

**3. Print the verdict last, then stop.** A script that prints `OK:` and then crashes attests clean. Prove everything first, announce at the end.

**4. No verdict line means UNATTESTED, not clean.** If the script is missing, unreadable, or produces nothing recognisable, the drill records `clean: null` and the Scan rung **blocks**. That is deliberate. A check that ran nothing must never report a pass.

## The skeleton

Copy this. It is the whole shape.

```bash
#!/usr/bin/env bash
# WHAT "GOOD" LOOKS LIKE, declared by the workload that owns it.
set -uo pipefail                      # NOT -e: we want our own FAIL line, not a bare exit
fail() { echo "FAIL: $*"; exit 1; }   # one line per message

# ... your checks here, cheapest and most fundamental first ...

echo "OK: <state precisely what you proved>"
exit 0
```

## The worked example (VM, in this repo)

From `infra/modules/azure-vm/cloud-init.yaml`. Five checks, five different questions. The first four ask *is the right data here?*. The fifth asks *does the store still work?*, which none of the others can answer.

```bash
# 1. the code came back
[ -x /opt/app/serve.sh ] || fail "/opt/app/serve.sh missing or not executable"
[ -s /opt/app/VERSION ]  || fail "/opt/app/VERSION missing"

# 2. the known-good marker survived — "what did we still trust?"
[ -s "$DATA/BASELINE" ] || fail "BASELINE marker missing — no known-good state in this recovery point"

# 3. the records are READABLE, not merely present
[ -s "$DATA/customers.csv" ] || fail "customers.csv missing — records lost"
rows=$(($(wc -l < "$DATA/customers.csv") - 1))
[ "$rows" -ge 1 ] || fail "customers.csv has no data rows"
head -1 "$DATA/customers.csv" | grep -q '^customer,' || fail "customers.csv header is corrupt"

# 4. nothing that signals an encryption event
locked=$(find "$DATA" -name '*.locked' | wc -l)
[ "$locked" -eq 0 ] || fail "$locked encrypted (.locked) files present"
[ ! -f "$DATA/README_RECOVER.txt" ] || fail "ransom note present"

# 5. can it ACCEPT and RETURN data, or only hold it? A synthetic transaction.
probe="$DATA/.verify-probe.$$"; token="resops-probe-$$"
{ echo "$token" > "$probe"; } 2>/dev/null \
  || fail "data store not writable — the recovery point cannot accept a transaction"
readback=$(cat "$probe" 2>/dev/null) \
  || { rm -f "$probe"; fail "data store not readable — wrote a record, could not read it back"; }
rm -f "$probe"
[ "$readback" = "$token" ] || fail "write/read mismatch in the data store"

echo "OK: code intact, baseline present, $rows customer records, no encryption markers, write/read verified"
```

**Why check 5 exists, and what it deliberately does NOT claim.** A read-only mount,
a full disk or a half-restored filesystem passes checks 1 to 4 and then fails a real
service on its very first write. Checks 1 to 4 read; check 5 writes, reads back,
compares and cleans up.

It proves the datastore accepts a write and returns the same bytes. **It does not
prove the application works.** Saying otherwise would make this script the exact
thing it exists to catch, which is a check claiming more than it examined.

Note the braces on the write. `echo ... 2>/dev/null` does not suppress the failure,
because the *redirect* is what fails on a read-only store and the shell reports that
itself, before `echo` runs. The drill's parser skips non-verdict lines so it would
still work, but a raw `Permission denied` above your `FAIL:` line is noise in the one
output a human reads at 2am.

## What makes a check worth writing

```
 GOOD                                    WEAK
 the file PARSES / the query RUNS        the file exists
 row counts within an expected range     the disk is the expected size
 a known-good marker is present          the timestamp looks recent
 schema / header is what you expect      the service starts
 no encryption or ransom markers         the process is running
 a write comes back as the same bytes    the mount point exists
```

The weak column is what a backup product can already tell you. Everything in the good column requires opening the data, which is exactly why the check has to live with the workload and not with the platform.

Aim for **cheap, deterministic, and readable in ten seconds by someone who did not write it**. Twenty lines is a good target. If it needs a test suite of its own, it is doing too much.

## How the verdict travels

```
 verify.sh  ──run inside the restored copy──▸  OK: / FAIL: line
     │
     ▼
 evidence/attestations/<workload>.json
     { source, clean, detail, at, restore_job, script }
     │                        └── WHEN matters as much as WHETHER
     ▼
 Scan rung          unattested → BLOCK · dirty → BLOCK · clean → climb
     ▼
 resops gate        stale attestation is a HARD hold, no override
                    (config/tiers.yaml · attestation_max_age_days)
```

`at` is why an attestation expires. "Verified once, a year ago" says nothing about the point you would restore today, so the gate enforces a per-tier age bar and there is deliberately no `--allow-stale` escape for it.

The workload must opt in by declaring `attestation_file:` in its config. With no attester declared, a workload is UNATTESTED and blocks. That is the honest default for anything nobody has actually checked.

## Other workload shapes

The contract does not change; only the checks do.

```
 VM image        restore, boot, run the script inside     ← implemented here
 managed DB      restore to a temp instance, run SQL      ← not written yet
 object storage  restore to a temp bucket, checksum       ← not written yet
```

Worked examples for the last two are outstanding. The shape is identical: prove the data parses, prove a known-good marker survived, prove nothing signals compromise, print one line, exit.
