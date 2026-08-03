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

Two cheap proxies were tried and both were blind:

```
 threat scan on the backup    never returned a verdict in a month. it CAN
                              be made to run on an Azure VM (README lists the
                              four things it needs), but ours stall in the
                              scan phase on a vendor-side fault. a signal you
                              cannot get an answer out of is not a signal.
 dedupe ratio as an           the same idle VM ranges 57.9%-99.7%.
   integrity signal           42 points of natural variance is noise, not signal.
```

Both were proxies. **There is no cheap way to know a backup is good. You have to open it and look.** That is why almost nobody does it, and why almost nobody actually knows.

So the attester is [`verify.sh`](VERIFY.md): the restore drill opens the recovery point in isolation and runs the workload's *own* check inside the restored copy. The one line it prints, `OK:` or `FAIL:`, is the attestation. Thirty lines of shell anyone in the room can read.

And an attestation has a shelf life. "Verified once, a year ago" is not verified, so freshness is policy (`config/tiers.yaml`, `attestation_max_age_days`) and a stale attestation is a hard HOLD with no override.

### The rule that came out of it

> **Absence of evidence is not evidence of absence.**
> A check that ran nothing must never report a pass.

We read "absent from the anomaly list" as "scanned and clean" for a month. Not one of those jobs had ever completed. `op threatscan` now refuses to report clean when `totalNumOfFiles` is 0, and the Scan rung blocks on an unattested point rather than inventing one.

The second lesson cost less and generalises further: **the job type shown in the console did not match the job type returned by the API.** Ten "completed" rows were a different operation entirely. Read your verifier's output from a second source before you believe it.

The third is about method, and it is the expensive one. We spent a month, and then a full day, black-box testing a feature against an eligibility rule we could not see. Each experiment was cheap and the answer always felt one more away. **A single conversation with someone who knew the product produced the missing piece in five minutes.** When you cannot see the rule, stop experimenting and go and ask. That is not a failure of rigour, it is the correct move for the shape of the problem.

This applies to your monitoring too. Go and check what your verifier actually verified.

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

- **The adapter is vendor-specific.** `client.py` + `reads.py`, 384 lines. The ladder, gate, evidence, crosswalk and metrics are not. Porting means implementing those reads, not rewriting the engine. No second adapter exists yet, so treat that as a clean seam rather than a proven claim.
- **The reference workload is a VM.** A bash service and a CSV. The *contract* transfers to a managed database or a bucket unchanged; worked examples for those are not written yet.
- **Restore-verify costs real money at production data volume.** The answer is sampling plus a per-tier freshness bar, not verifying everything every day. There is no cost model here yet.
- **The compliance crosswalk is indicative.** It supports a resilience programme. It is not a formal attestation.
- **Nobody owns this by default.** The gate belongs to CI, `verify.sh` to the app team, the drill to platform, the policy to risk. In most organisations that spans three teams who do not currently talk about recovery together. The org problem is usually larger than the technical one.
