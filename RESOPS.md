# ResOps, made executable

> This file is about the **idea**. [README.md](README.md) is about running the tool.

## The observation

Every property that gates your production has a check that runs and returns an exit code.

```
 tests            pytest            exit 0 / 1
 style            lint              exit 0 / 1
 vulnerabilities  scanner           exit 0 / 1
 policy           conftest / OPA    exit 0 / 1
 drift            terraform plan    exit 0 / 2
 recoverability   —                 —
```

Recoverability is the only production-critical property with no such check. Not because it matters less. Because nobody built the check.

That is the entire idea. Everything below is supporting material.

## ResOps in one paragraph

ResOps (Resilience Operations) is an operational discipline that unites security, infrastructure and operations around critical services, resilient design, and **continuous validation**. Its own framing is the important part: *a practice and discipline that can be adopted, not a product that can be bought*, moving teams *from assumption-based resilience to evidence-based, measurable, predictable recoverability*. The framework is Commvault's; the mechanism in this repo is one way to run it.

A discipline that cannot be bought needs a reference implementation rather than a datasheet. This repo is one.

## It is the test model, pointed at recovery

Nothing here is new to a platform engineer except the right-hand column existing at all. That is why it transfers.

```
 YOU ALREADY HAVE         RESOPS EQUIVALENT          WHO OWNS IT
 a test                →  verify.sh                  the app team
 a test runner         →  the restore drill          the platform team
 a required check      →  resops gate  exit 0 / 1    CI
 "tests ran recently"  →  attestation freshness      policy / risk
 coverage %            →  resops metrics             the wall
```

If you can explain code coverage to someone, you can explain this to them.

## Where the repo sits in the five domains

```
 1  Resilience governance     define practices and outcomes    config/tiers.yaml
 2  Recovery planning         a roadmap to resilience          the ladder + blocked stage
 3  Recovery architecture     clean, fast, end-to-end          infra/ paved road
 4  Resilience by repetition  validating and PROVING           the drill + freshness bar
 5  Measuring resilience      tracking what matters            resops metrics + crosswalk
```

Domains 4 and 5 are where the mechanism matters most, because they are the two the industry asserts and rarely operates.

## The ladder is the ResOps loop, with the trust question split out

```
 RESOPS LOOP                        THIS REPO
 discover                      →    Discover    onboarded for protection?
 protect                       →    Protect     a policy attached?
 detect (anomalies/changes)    →    Detect      last backup clean?
 recover (clean trusted data)  →    Recover     is there a recent recovery point?
                                    Scan        is that point TRUSTWORTHY?
 restore (business systems)    →    Validate    did a real restore prove it?
```

The first four names are the loop's, verbatim. The one thing this adds is splitting *recover* into two questions, because a recovery point that exists and a recovery point you can trust are not the same claim, and conflating them is how a backup that "completed successfully" gets restored into an incident.

**The ladder answers WHETHER. The gate answers WHETHER IT'S GOOD ENOUGH** (freshness, RPO/RTO, regression). A workload sits on exactly one rung; you stop at the first stage that doesn't clear, and that rung *is* the state. The blocked stage names the fix.

## The hard part: who attests

Everything above is bookkeeping until something can honestly say *this recovery point is safe to restore from*. That is the only genuinely difficult question in resilience, and it is where we spent the most and learned the most.

Two cheap proxies were tried. One is noise. The other works, and is still not enough on its own:

```
 threat scan on the backup    WORKS. 2026-08-12: two planted EICAR files
                              found inside an Azure VM image backup, with a
                              clean scan either side of the dirty one. It
                              also missed fourteen encrypted files that
                              verify.sh caught. A second attester, not a
                              substitute.
 dedupe ratio as an           the same idle VM ranges 57.9%-99.7%.
   integrity signal           42 points of natural variance is noise, not signal.
```

**There is no way to know a backup is good without opening it and looking.** The vendor's scan does open it, and looks for what *it* recognises. Only your own check knows whether *your* service still works. That is why you want both, and why almost nobody has either.

So the attester is [`verify.sh`](VERIFY.md): the restore drill opens the recovery point in isolation and runs the workload's *own* check inside the restored copy. The one line it prints, `OK:` or `FAIL:`, is the attestation. Thirty lines of shell anyone in the room can read.

And an attestation has a shelf life. "Verified once, a year ago" is not verified, so freshness is policy (`config/tiers.yaml`, `attestation_max_age_days`) and a stale attestation is a hard HOLD with no override.

### The rule that came out of it

> **Absence of evidence is not evidence of absence.**
> A check that ran nothing must never report a pass.

We read "absent from the anomaly list" as "scanned and clean" for a month. The Scan rung now blocks on an unattested point rather than inventing one.

The rule survived a correction; the story we told about it did not. We also spent six weeks asserting those scans had never examined anything, on the strength of a field that job type does not populate at all. On 2026-08-12 one of them found two planted EICAR files. **The rule was right for a reason we had wrong**, which is its own lesson about how comfortable a good rule can make you.

The second lesson cost more and generalises further: **we identified an operation by a field that was never meant to name it.** `opType` and `jobType` describe the job *kind*; `localizedOperationName` describes the *operation*, and for threat analysis those two permanently disagree inside the same record. We read `opType`, concluded "file indexing, not a scan", and built six weeks on it. The console had been right the whole time.

> Before you conclude what something *is* from one field, find out what that field was for.

The third is about method, and it is the expensive one. We spent a month, and then a full day, black-box testing a feature against an eligibility rule we could not see. Each experiment was cheap and the answer always felt one more away. **A single conversation with someone who knew the product produced the missing piece in five minutes.** When you cannot see the rule, stop experimenting and go and ask. That is not a failure of rigour, it is the correct move for the shape of the problem.

The fourth is ours, in this repo's own code, and it is the one we would least like to have found. **The top rung of this ladder, the one that says recovery is *proven*, accepted a 194-byte file download as proof.** It asked the vendor's job history for the newest restore job mentioning this workload, and a console file download satisfied both conditions honestly: the restore filter includes downloads, and the workload's name is in the record. Nothing was restored. Nothing was booted. Our own check never ran. The gate said PROMOTE and exited 0.

The tempting fix is to tighten the match, and that is the same mistake one level up. The real error was **asking an open-world list a question only a closed-world record can answer.** We do not control what that filter returns, so any rule over it is a guess about a category we cannot enumerate — and meanwhile the drill that did the work had already written down the exact job it ran.

> **Do not re-derive what you were told.**
> When your own code did the work and recorded it, that record is the evidence. The vendor's job is to confirm it, not to be searched for it.

This applies to your monitoring too. Go and check what your verifier actually verified — and note that we only found ours by *deliberately trying to fool it*, not by reading it. It had looked correct for as long as it had existed.

## Adopting it

```
 L1  SEE       resops gate, read-only. learn your real number.        day 1
 L2  DECLARE   write verify.sh for ONE tier-1 workload. 20 lines.     week 1
 L3  PROVE     one scheduled drill. one attestation.                  week 2
 L4  GATE      required CI check on that ONE workload. ratchet.       month 1
 L5  PUBLISH   resops metrics on a wall. % provably recoverable.      quarter 1
```

L1 is the whole adoption story: read-only, physically cannot mutate your environment (there is a test enforcing that), and it tells you your real position by Monday.

**L4 is where adoption usually dies**, because a real estate goes red on day one and the check gets deleted by Friday. Use `enforce_from:` — a declared, dated tolerance that never changes a workload's verdict, only whether that verdict blocks the aggregate, and that expires by itself. See the README section *Turning it on without everything going red*.

## Honest limits

- **The vendor coupling is wider than the adapter, and this correction is recent.** `client.py` + `reads.py` (~450 lines) do the I/O, and `gate()`, the evidence chain, the crosswalk, the metrics and the renderer are genuinely vendor-neutral. **But `classify()` — the ladder itself — reads Commvault's field names directly** (`slaCategoryDescription`, `lastSuccessfulBackupTime`, `vmBackupInfo`, `lastBackup.failureReason`). So porting today is not "implement those reads": it is "implement reads that emulate Commvault's JSON shape", which asks a porter to learn a foreign vendor's schema to satisfy an engine that claims not to care about it. A neutral facts seam between the adapter and the ladder is designed and not built. Until it is, treat portability as an *intention* rather than a clean seam, and certainly not a proven claim.
- **The reference workload is a VM.** A bash service and a CSV. The *contract* transfers to a managed database or a bucket unchanged; worked examples for those are not written yet.
- **Restore-verify costs real money at production data volume.** The answer is sampling plus a per-tier freshness bar, not verifying everything every day. There is no cost model here yet.
- **The compliance crosswalk is indicative.** It supports a resilience programme. It is not a formal attestation.
- **Nobody owns this by default.** The gate belongs to CI, `verify.sh` to the app team, the drill to platform, the policy to risk. In most organisations that spans three teams who do not currently talk about recovery together. The org problem is usually larger than the technical one.
