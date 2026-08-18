# Resilience, Shifted Left

> **Participant guide, two hours.** Every command is copy-paste. You should never
> type a path from memory. The facilitator floats.

**Level** 300-400 · **Duration** 2h · **Audience** platform engineers, SREs, cloud
architects, and the people who fund them

There is a longer form of this day: [WORKSHOP.md](WORKSHOP.md) is 6h35m and it
teaches you to **write** an attester. This one is two hours and it teaches you to
**win the argument**. They are not two versions of the same thing.

---

## The one idea

```
 You gate on tests.
 You gate on security scans.
 You do not gate on recoverability.
```

Three of those moved left already. The fourth has not.

## What you leave with

Not a finished lab. An argument you have already made out loud, to someone who
tried to break it, plus one dated action for a workload you actually own.

```
 ACT I    RECOGNITION             7m   you have done this three times
 ACT II   THE GATE, TWICE        27m   one required check, two answers
 ACT III  WHAT YOU DO ABOUT IT   27m   the choice, and the merge blocker
 ACT IV   OWN IT                 30m   break the argument, then commit
```

```
 OFFLINE   no cloud, no token, instant, cannot fail
 LIVE      a real Azure VM, provisioned and climbed before you arrived
```

You will not spend this session on terraform. Your workload is already at
`VALIDATED`.

### Before you start

```bash
cd ~/resops-cvlt-azure
source .venv/bin/activate
```

```
 ✓ YOU SHOULD SEE   the prompt change to (.venv)
 ✗ IF NOT           ask. everything below depends on it.
```

---

# ACT I · RECOGNITION

**7 minutes · no commands**

## Beat 1 · The fourth gate

You have taken a whole class of failure and moved it from *we find out in
production* to *we find out at the pull request*. Three times.

```
 SHIFTED LEFT ALREADY              STILL ON THE RIGHT
 tests       -> CI gate            recoverability -> a ticket,
 security    -> scanner gate                        after an outage
 infra       -> plan gate
 lint        -> merge blocker
```

Each time it was the same fight. Each time nobody argued after the first year.

**WORKSHEET 1. Write it, fold it, hand it in.** You get it back at the end.

```
 1. What % of your production estate could you PROVE is recoverable?
 2. How would you prove it, to someone who did not believe you?
 3. How long would producing that proof take?
```

```
 ? WHY THIS MATTERS
   It is the only measurement this session makes. If your answer at the
   end is the same as now, we wasted your time and we want to know.
```

---

# ACT II · THE GATE, TWICE

**27 minutes · LIVE**

One required check. Two answers. A gate that only ever says yes is not a gate.

## Beat 2 · The gate says yes · 10 min

```bash
python3 -m resops.operator.op status infra/workloads
```

```
 ✓ YOU SHOULD SEE   ●●●●●●  VALIDATED
                    six stages cleared, and a reason beside each one
 ✗ IF NOT           tell the facilitator your codename. do not debug it.
```

```bash
python3 -m resops.operator.op gate infra/workloads
```

```
 ✓ YOU SHOULD SEE   PROMOTE  recoverability proven · exit 0
 ✗ IF NOT           if it says HOLD and names COVERAGE, a scheduled backup
                    ran overnight. That is not your fault and it is not a
                    bug — ask, and keep reading. You will meet that exact
                    behaviour again in twenty minutes.
```

Now look at the bar it passed. It is not one threshold, it is a per-tier one:

```bash
cat config/tiers.yaml
```

```
 ✓ YOU SHOULD SEE   tier1 and tier2, each declaring rpo_hours, rto_minutes
                    and attestation_max_age_days
```

```
 ? WHY THIS MATTERS
   A measurable, testable target per critical service is a Service
   Resilience Indicator. Read the NOTE at the bottom of that file: nobody
   restore-verifies everything every day, so the policy is not "everything
   is verified", it is "for THIS tier, something must have opened a
   recovery point and read it within N days".

   A tier that declares no freshness value is never checked for it. That
   is a legitimate choice, made explicitly, and still recorded.
```

Then read what actually produced the verdict:

```bash
grep -A 40 'path: /opt/app/verify.sh' infra/modules/azure-vm/cloud-init.yaml
```

```
 ✓ YOU SHOULD SEE   twenty-five lines of shell. Five checks.
                    the last one WRITES a record and reads it back.
```

```
 ? WHY YOU READ IT HERE AND NOT OVER SSH
   That VM has no public IP, no inbound rule, no open ports. You cannot
   reach it and neither can anything else. The only way in is the guest
   agent, which is exactly how the drill runs this script INSIDE the
   restored copy.

   The workload being unreachable is the point. The attester still ran.
```

Four of the five checks ask *is the right data here?*. The fifth asks *does the
store still work?*, which none of the others can answer. A read-only mount passes
the first four and fails a real service on its first write.

## Beat 3 · Recoverable to what? · 5 min

**No commands. No slides.**

You have just proved this workload is recoverable.

```
                    Recoverable to WHAT?
```

Sit with it. Then:

```
                    And which recovery point is that claim about?
```

```
 ? THE TERM THIS PRODUCES
   The distance between what you think you can recover and what you can
   prove is your RESILIENCE GAP.
```

## Beat 4 · The gate says no · 12 min

Now break it. On purpose, with something harmless and detectable.

```bash
python3 -m resops.operator.op incident infra/workloads
```

```
 ✓ YOU SHOULD SEE   planted: 2 EICAR files, 14 .locked files, 1 note
                    BASELINE marker still present: yes
 ✗ IF NOT           if it cannot reach the VM, ask. Nothing after this works.
```

EICAR is the industry-standard harmless test pattern every scanner is built to
detect. The `.locked` files are high-entropy junk with a changed extension, which
is what mass encryption looks like on disk. Nothing is really encrypted.

```bash
python3 -m resops.operator.op backup infra/workloads
```

```
 ✓ YOU SHOULD SEE   a backup job, then  backup Completed
 ✗ IF NOT           a 5-15 minute queue is NORMAL on a first run. It is
                    waiting for a media agent slot, not failing.
```

```
 ? WHAT YOU ARE WATCHING
   Your own planted compromise being committed into a recovery point.
   The job says Completed. It is green. It is correct. Nothing is broken,
   which is exactly what makes it dangerous.
```

```bash
python3 -m resops.operator.op gate infra/workloads
```

```
 ✓ YOU SHOULD SEE   HOLD · exit 1
                    ↳ attestation does not cover the newest recovery point
```

```
 ? WHY THIS MATTERS — and nobody predicts this one

   You did not change the verdict. You took a BACKUP.

   An attestation is a claim about ONE recovery point, not a property of
   the workload. There is now a newer point and nothing has opened it, so
   the proof you had ten minutes ago vouches for nothing. Most people
   expect proof to accumulate. It does not.

   This is your resilience gap, measured, in one line.
```

Now ask the threat lane what it thinks:

```bash
python3 -m resops.operator.op threatscan infra/workloads
```

```
 ✓ YOU SHOULD SEE   THREATS DETECTED · exit 1
                    the scan ran, and this recovery point is NOT safe
 ✗ IF NOT           if it stops asking for scan_plan_id, tell the
                    facilitator and move on. The lesson above already landed.
```

```
 ? WHY THIS MATTERS
   Two HOLDs, two different reasons. The first said "nothing has looked
   at this point". The second said "something looked, and found malware".

   Those are opposite situations and they must never read the same. A
   check that examined nothing must never report a pass.
```

**Where you are now.** Your backup job said Completed. The restore said
Completed. The VM is healthy. Every signal the backup platform gave you was
green, and the recovery point you would have restored from is poison.

---

# ACT III · WHAT YOU DO ABOUT IT

**27 minutes**

## Beat 5 · The hard choice · 15 min · OFFLINE

First, put your own workload back. This runs while you do the exercise.

```bash
python3 -m resops.operator.op remediate infra/workloads
```

```
 ✓ YOU SHOULD SEE   it removes exactly what the incident planted, restores
                    exactly what it took, then re-runs verify.sh
                    the last line starts  OK:
 ✗ IF NOT           it raises rather than reporting success. Tell the
                    facilitator. Do not re-run it twice.
```

Now the exercise. Four recovery points, no cloud, no token:

```bash
python3 -m resops gate config/incident.yaml
```

```
 ✓ YOU SHOULD SEE

   ▸ D-7-hours-ago      ●●●●●●  VALIDATED   RPO 7.0h      PROMOTE
   ▸ C-32-hours-ago     ●●●●✗·  blocked at Scan           HOLD
     ↳ recovery point is UNATTESTED
   ▸ B-6-days-ago       ●●●●●●  VALIDATED   RPO 144.0h    HOLD
     ↳ rpo 144.0h > target 8h
   ▸ A-400-days-ago     ●●●●●●  VALIDATED   RPO 9600.0h   HOLD
     ↳ attestation stale (400.0d > 30d)
```

**The fact you do not have:** the first anomalous log entry is *"sometime last
week"*. Retention is seven days and the earliest surviving entry is already
abnormal. It may have started three days ago. Or nine.

**Choose one. Justify it in a sentence, naming what you give up.**

```
 ? WHY THIS MATTERS

   The gate promotes exactly one point, and it is the one squarely inside
   the incident window. That is not a bug. It is a policy written for
   OUTAGES answering a question about COMPROMISE.

   An RPO target assumes the only cost of an older point is LOST DATA.
   Under compromise, the freshest point is the most DANGEROUS one.

   And look at A. The only point anyone can be certain about costs 400
   days of orders — and it is only certain because NOTHING WAS VERIFIED
   between it and last week. That gap is not bad luck. It is the drill
   nobody scheduled.
```

```
 ? THE NUMBER THIS PRODUCES
   The clock starts when a human authorises a clean recovery and stops
   when a human signs the service back off. Everything between is
   automatable and measurable.

   That is Mean Time to Clean Recovery. Not time to recovery. Time to
   CLEAN recovery. The word "clean" is the entire argument.
```

## Beat 6 · Make it a merge blocker · 12 min · OFFLINE

```bash
python3 -m resops gate config/estate.yaml
```

```
 ✓ YOU SHOULD SEE   six workloads, five of them HOLD, and a final line
                    AGGREGATE  HOLD — checkout-api, identity-svc,
                                      reporting-db, edge-cache, legacy-batch
                    exit 1
```

**Stop on `checkout-api` and `identity-svc`.** Same rung. Opposite reasons. One
was tested and is contaminated; one was never tested at all. The rung hides that.
The blocked stage names it.

```bash
python3 -m resops metrics config/estate.yaml
```

```
 ✓ YOU SHOULD SEE   Prometheus text — resops_rung, resops_promotable,
                    resops_tolerated
 ✗ IF NOT           "no run to publish" means you skipped the gate command
                    above. Run it first; metrics publishes the LAST run.
```

```bash
cat .github/workflows/resops-gate.yml
```

```
 ✓ YOU SHOULD SEE   about twenty lines. on pull_request, and daily.
```

```
 ? THE OBJECTION THIS ANSWERS
   Point this at a real estate and almost everything HOLDs on day one.
   Correctly. But then nobody can ship, so the check gets deleted by Friday.

   So a workload can declare a DATED tolerance:

       enforce_from: 2027-01-01
       tolerance_reason: "backup policy rebuild in flight"

   It still HOLDs, on screen and in the report. Only the aggregate stops
   counting it, and only until that date. A DATE, not a flag — a flag is
   permanent the moment somebody forgets it. And resops_tolerated
   publishes how many you have, so it is a number that has to go down.
```

```
 WHO OWNS WHAT — the argument you will have when you get back

   verify.sh    the app team      only they know what "good" means
   the drill    platform          it is infrastructure
   the gate     CI                it is a required check
   tiers.yaml   platform + risk   it is policy
```

```
 ? DOES THIS PAGE ME AT 3AM?
   No. Recoverability drift is not an incident. It fails a pull request
   and waits for office hours.
```

---

# ACT IV · OWN IT

**30 minutes · no commands**

## Beat 7 · Break the argument · 20 min

You are going to have this argument next week, with someone who has not been
here. So have it now, with someone who has.

```
 05 min   What will your staff engineer say to kill this?
          Call them out. No answers yet. Just collect them.

 10 min   Answer each other's. The facilitator adds the ones nobody raised.

 05 min   Write the ONE objection you will actually face, and your answer.
          Hand it in.
```

**Your ammunition. Pick three.**

```
 1  We gate on tests. We gate on scans. We do not gate on recoverability.

 2  A green backup dashboard is a build artefact, not a run signal. It
    proves the job ran, not that the data is recoverable.

 3  Available is not trusted. The distance between them is our
    resilience gap.

 4  A check that examined nothing must never report a pass.

 5  The number is time to CLEAN recovery. Not time to recovery.

 6  This is not a page at 3am. It is a merge blocker.
```

```
 ? WHY THIS AND NOT A SUMMARY SLIDE
   An argument you have never said out loud does not survive a design
   review. Writing it down is not the same as having made it.
```

## Beat 8 · One action · 10 min

Unseal worksheet 1. Write today's number beside it.

```
 L1  SEE       resops gate, read-only, your own number       day 1
 L2  DECLARE   verify.sh for ONE tier-1 workload             week 1
 L3  PROVE     one scheduled drill, one attestation          week 2
 L4  GATE      one required check, with the ratchet          month 1
 L5  PUBLISH   % provably recoverable, on a wall             quarter 1
```

**What L1 actually needs, so nobody is surprised on Monday:**

```
 1  an access token from Command Center (avatar -> Access Tokens)
 2  your tenant's API endpoint
 3  two ids from a console URL: the hypervisor, and the protection plan
 4  the workload's group — `resops list` finds it by name
```

L1 is read-only and **physically cannot mutate your environment.** The engine
makes no create, update or delete calls of any kind, and a test in the suite
fails if anyone adds one. That is the point of starting there: it costs an
afternoon and risks nothing.

**One next action. Named workload. Dated. Owner.** Not three.

```
 In seven days there is one question: did you run it against anything real?
```

---

## What is honestly not solved

```
 the lab workload is a VM       the contract transfers to managed DBs,
                                buckets and clusters; the worked examples
                                are not written
 restore-verify costs money     sampling plus a per-tier freshness bar is
                                a POLICY, not a cost model. We have none.
 the crosswalk is INDICATIVE    it supports a resilience programme. It is
                                not a formal attestation.
 nobody owns this by default    it spans three teams who mostly do not
                                talk about recovery together
```

Both of the first two are real gaps, and both are ours.

## Further reading

[RESOPS.md](RESOPS.md) the idea · [VERIFY.md](VERIFY.md) the attester contract ·
[README.md](README.md) running the toolkit yourself ·
[WORKSHOP.md](WORKSHOP.md) the 6h35m form, which teaches you to write one
