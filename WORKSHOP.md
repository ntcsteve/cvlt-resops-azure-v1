# Trusted Recovery for Cloud-Native Workloads

> **Participant guide.** Work at your own pace. The facilitator floats.
> Every command is copy-paste. You should never type a path from memory.

**Level** 300-400 · **Duration** 7h10m door to door · **Audience** platform engineers, SREs, cloud architects

Facilitators: read [FACILITATOR.md](FACILITATOR.md) first. Worksheets: [WORKSHEETS.md](WORKSHEETS.md).

---

## The one idea

```
 You gate on tests.
 You gate on security scans.
 You do not gate on recoverability.
```

Everything today supports that sentence. If you leave with nothing else, leave with the question it implies: *how much of your estate could you prove is recoverable right now, to someone who did not believe you?*

## How the day runs

```
 M1  Broken trust                    60m   what can you still trust?
 M2  Recoverability as code          50m   the check, and how it becomes a default
 M3  The Trusted Recovery Pattern    50m   the decision model you take home
 M4  Verify your verifier            30m   the most transferable 30 minutes today
 M5  Lab — declare and prove         75m   you write an attester
 M6  Game day                        75m   break it, then choose
     Close                           15m
```

```
 OFFLINE   no cloud, no token, one second, cannot fail
 LIVE      a real Azure VM, already provisioned for you
 WATCH     the facilitator drives; you do not need to follow along
```

Your workload was provisioned and climbed to VALIDATED before you arrived. You will not spend the morning on terraform.

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

# M1 · Recovery under broken trust

**60 minutes · OFFLINE**

**Objective:** establish that a service can be fully available and still be operationally untrusted, and produce the trust map you will be scored against in M6.

## 1.1 · See the gap · 10 min

An estate of six workloads. One command.

```bash
python3 -m resops gate config/estate.yaml
```

```
 ✓ YOU SHOULD SEE   six workloads, each rendered like this —

   ▸ payments-api  prod  payments  (critical)
     ●●●●●●  VALIDATED  ·  RPO 3.0h
     ↳ recovery proven — job 884730
     PROMOTE  recoverability proven · exit 0

   ▸ checkout-api  prod  payments  (critical)
     ●●●●✗·  RECOVERABLE  ·  RPO 4.0h  blocked at Scan
     ↳ recovery point failed restore-verify — 14 encrypted (.locked) files present
     HOLD  ... · exit 1

   — and four more blocked at Validate, Detect, Recover and Discover,
   then a final line:

   AGGREGATE  HOLD — checkout-api, identity-svc, reporting-db,
                     edge-cache, legacy-batch · exit 1

 ✗ IF NOT   `pip install -e .` then try again.
```

The **bar** is the six stages. The **state** is where you stopped. **blocked at** names the stage that did not clear.

**Stop on `checkout-api`.** Protected. Backups completing. SLA met. Recovery *proven* by a real restore. Every light green, and it still must not ship, because the point it would restore from carries a threat.

```
 ? WHY THIS MATTERS

   Available is not the same as trusted. Every other row is a problem
   you already know how to describe. That one is not, and it is why
   the Scan stage exists.

   checkout-api and identity-svc sit on the SAME rung for opposite
   reasons — one was tested and is contaminated, one was never tested.
   The rung hides that. The blocked stage names it.
```

## 1.2 · Your number · 5 min · WORKSHEET 1

Write your answer. Fold it. Hand it to the facilitator. You get it back at the close.

```
 1. What percentage of your production estate could you PROVE
    is recoverable today?
 2. How would you prove it, to someone who did not believe you?
 3. How long would producing that proof take?
```

```
 ? WHY THIS MATTERS

   This is the only measurement the day makes. If your answer at the
   close is the same as now, we wasted your time and I want to know.
```

## 1.3 · Trust map · 35 min · WORKSHEET 2

### The scenario

`orders-api` is a tier-1 payments service. 41,892 customer records.

A deployment landed on Tuesday. A storage credential with broad access was over-permissioned and has been used from an address nobody recognises. This morning there is a file called `README_RECOVER.txt` in the data directory.

The service is still responding. Requests are being served. Dashboards are green.

### The four categories

Every workload, at any size, is made of four things. Yours has forty services and six managed stores. It is still these four categories, just more of each.

```
 CODE       what executes            did this come from the pipeline?
 STATE      what it has written      it changed after the deploy. expected?
 CONFIG     what shapes behaviour    who can write this?
 IDENTITY   what it can reach with   this is the blast radius
```

In today's lab those are four things you can point at:

```
 CODE      /opt/app/serve.sh · /opt/app/VERSION
 STATE     /var/lib/app/data/  (customers.csv · orders.ndjson · BASELINE)
 CONFIG    /etc/app/config.yml       world-readable, on purpose
 IDENTITY  /etc/app/creds.env        the storage key
```

### The exercise

Mark each, and justify it in one line.

```
 TRUSTED     I would run production on this as-is, and here is why
 UNTRUSTED   I have positive reason to doubt it
 UNKNOWN     I have no evidence either way
```

Then two harder questions:

```
 4. What single missing fact would move the most boxes out of UNKNOWN?
 5. Your backups. Trusted, untrusted or unknown — and why?
```

```
 ? WHY THIS MATTERS

   UNKNOWN is the honest answer far more often than people write, and
   a box you cannot justify is worth more today than a confident one.
   Question 5 is what the rest of the day answers.

   KEEP THIS SHEET. In M6 you find out which boxes you got right,
   and it is scored.
```

**M1 outputs:** a sealed number · a trust map · a question you cannot yet answer.

---

# M2 · Recoverability as code

**50 minutes · OFFLINE**

**Objective:** turn the ladder into a check that runs in CI, and work out how it becomes a default rather than a heroic one-off.

## 2.1 · Read the bar · 10 min

No command. Look at these four and answer two questions each: **which stage failed, and what is the fix?**

```
 A   ●●●✗··   MONITORED
 B   ●●●●●✗   RECOVERABLE
 C   ✗·····   UNDISCOVERED
 D   ●●●●✗·   RECOVERABLE
```

```
 ✓ ANSWERS
   A  Recover   — backups are green but the RPO/SLA bar is missed
   B  Validate  — recoverable on paper, no restore has ever proven it
   C  Discover  — nobody onboarded it
   D  Scan      — the point you would restore from is not trusted

   B and D are the same rung, different problems. That distinction is
   the whole reason the tool names a stage instead of a score.
```

## 2.2 · The ratchet · 15 min

Point this at a real estate and almost everything HOLDs on day one. Correctly. But nobody can ship, so the check gets deleted by Friday, and the only tool that told you the truth is gone.

Open `config/estate.yaml`, find `reporting-db`, and uncomment these two lines:

```yaml
    enforce_from: 2027-01-01
    tolerance_reason: "backup policy rebuild in flight"
```

```bash
python3 -m resops gate config/estate.yaml
```

```
 ✓ YOU SHOULD SEE

   HOLD  stuck at PROTECTED: last backup not clean ... · exit 1
   ↳ TOLERATED until 2027-01-01 — still a HOLD, excluded from the
     aggregate until that date

   AGGREGATE  HOLD — checkout-api, identity-svc, edge-cache,
                     legacy-batch · 1 TOLERATED (reporting-db) · exit 1

 ✗ IF NOT   exit 2 means a malformed date. it must be YYYY-MM-DD.
```

Now put it back:

```bash
git checkout config/estate.yaml
```

```
 ? WHY THIS MATTERS

   reporting-db STILL HOLDS. On screen, in the bundle, in the report.
   Only the aggregate stopped counting it, and only until that date
   arrives on its own.

   A bypass hides a gap. This declares one, counts it, and expires by
   itself. It is a date and not a flag because a flag is permanent the
   moment someone forgets it.

   The count publishes as resops_tolerated, so "we have 3 unenforced"
   becomes a number on a wall that has to go down.
```

## 2.3 · Twenty lines of CI · 10 min

```bash
cat .github/workflows/resops-gate.yml
python3 -m resops metrics config/estate.yaml
```

```
 ✓ YOU SHOULD SEE   a workflow that runs on pull_request and daily,
                    then Prometheus text including resops_rung,
                    resops_promotable and resops_tolerated

 ? WHY THIS MATTERS
   Judge once, publish many. The metrics read evidence a run already
   wrote — no tenant, no network, no agent on any workload.
```

## 2.4 · Making it the default · 15 min

Discussion, no commands. The two questions this room always asks.

```
 "HOW DOES THIS BECOME A DEFAULT FOR 200 SERVICES?"

   infra/platform/   the paved road — hypervisor, storage, one policy
                     per tier. Platform team owns it. Built once.
   config/tiers.yaml THE policy. RPO, RTO, attestation freshness.
   an app team       declares `tier: tier1` and inherits every bar.

   They do not configure recoverability. They choose a tier.

 "DO I WRITE 200 verify.sh FILES?"

   No. One per workload SHAPE, not per workload. A template per
   archetype — VM, managed DB, bucket, queue. Most teams have four
   or five shapes and think they have two hundred.

 "DOES THIS PAGE ME?"

   NO. And this is the most under-sold point of the day.
   Recoverability drift is not an incident. It is a MERGE BLOCKER.
   It fails a pull request. It does not wake you up. The blocked
   stage names the fix and it waits until Tuesday.
```

```
 WHO OWNS WHAT — write this down, it is the argument you will have
                 when you get back

   verify.sh          the app team      only they know what "good" is
   the drill          platform          it is infrastructure
   the gate           CI                it is a required check
   tiers.yaml         platform + risk   it is policy
```

**M2 outputs:** a gate config you edited · the ownership split · three answers.

---

# M3 · The Trusted Recovery Pattern

**50 minutes · WORKSHEET 3**

**Objective:** leave with a reusable decision model, not an impression.

## 3.1 · The five steps · 10 min

```
 1  Map trust boundaries        what is trusted, untrusted, unknown
 2  Find trusted protected      which copies survived the same blast radius
    state
 3  Label recovery points       which are clean, which are suspect,
                                and which has nobody looked at
 4  Choose or construct the     newest may be risky, oldest may be
    cleanest viable point       too lossy
 5  Capture evidence and        what was protected, what was trusted,
    learning                    what was restored, and why
```

You did step 1 in M1. You do step 3 in M5, step 4 in M6, step 5 at the close.

## 3.2 · Write it for the scenario · 25 min · WORKSHEET 3

Using the trust map you already made, write one or two concrete actions per step. Not elegant phrasing. Operational clarity — what you would actually do on the morning you found that ransom note.

## 3.3 · The blast radius question · 15 min

Most tables write something like *"restore from backup"* at step 2. So:

```
 Is your backup inside the blast radius?

 The credential that was misused — could it reach your backups?
 Could it delete them? Could it change their retention?
 Who would know if it had?
```

**→ AIR GAP PROTECT** is shown here, in the console, as the answer to the question you just asked yourself. Immutable, isolated copies that the compromised credential cannot reach.

```
 ? WHY THIS MATTERS

   Notice the pairing, because the whole day is built on it:

     the UI DECLARES it        an air-gapped, immutable pool
     the code VERIFIES it      the Protect stage confirms the plan
                               is actually attached, on every run

   A control you declared and never verified is a control you hope
   you have.
```

**M3 output:** a Trusted Recovery Pattern for the scenario.

---

# M4 · Verify your verifier

**30 minutes · WORKSHEET 4**

**Objective:** the most transferable thirty minutes of the day, and it is not about backup.

## 4.1 · Ship or hold? · 20 min

The facilitator shows a real threat scan job record from a real tenant.

```
 status       Completed
 anomalies    none recorded
 verdict      ?
```

**Vote. Out loud, hands up, before anything else is said.**

Then the facilitator reveals what else that record says, and what it cost us to not look.

```
 ? THE RULE THIS PRODUCES

   Absence of evidence is not evidence of absence.
   A check that ran nothing must never report a pass.
```

You will then be shown the two places that rule is enforced in code, rather than asserted on a slide.

## 4.2 · Three checks in your pipeline · 10 min · WORKSHEET 4

```
 Name three checks in YOUR pipeline that could pass having
 examined nothing.
```

Starters, if you need them:

```
 a test filter matched 0 tests and the runner exited 0
 a scanner with no ruleset loaded for that language
 a coverage gate where the coverage file was never produced
 terraform plan against an empty workspace
 a smoke test that got 200 from a CDN cache, not the app
 an alert on a metric that stopped being emitted
```

```
 ? WHY THIS MATTERS

   That last one. Your alert did not fire. Was everything fine, or
   did the metric stop being emitted? Every SRE in this room has
   that scar. This lesson is not about backup at all.
```

**M4 output:** three named checks you will go and verify.

---

# M5 · Lab — declare and prove

**75 minutes · LIVE**

**Objective:** author an attester. This is the one thing nobody can write for you.

## 5.1 · Your workload · 20 min

It was climbed to VALIDATED before you arrived.

```bash
op gate infra/workloads
```

```
 ✓ YOU SHOULD SEE   ●●●●●●  VALIDATED
                    PROMOTE  recoverability proven · exit 0

 ✗ IF NOT           tell the facilitator your codename. do not debug it.
```

Now read the thing that actually produced that verdict:

```bash
cat /opt/app/verify.sh        # on your workload, via the console or ssh
```

Thirty lines of shell. Four checks. Read it in ten seconds. Full contract in [VERIFY.md](VERIFY.md).

## 5.2 · Write a check for YOUR shape · 35 min

**Pick the shape you actually run.** Not the one in the lab.

```
 VM               bash, runs inside the restored copy
 MANAGED DB       restore to a temp instance, run SQL
 OBJECT STORAGE   restore to a temp bucket, checksum + schema probe
 KUBERNETES       restore, apply, probe
```

Write the checks. Pseudocode is worth exactly as much as bash — the contract is four rules and none of them are language-specific:

```
 1  the verdict LINE is authoritative      OK: / FAIL:
 2  ONE line per message                   the parser stops at the first
 3  print the verdict LAST                 then exit
 4  no verdict means UNATTESTED            never clean
```

Aim for checks in the left column, not the right:

```
 GOOD                                WEAK
 the file PARSES                     the file exists
 row counts in an expected range     the disk is the expected size
 a known-good marker is present      the timestamp looks recent
 schema is what you expect           the service starts
```

The right column is what a backup product can already tell you. The left column requires opening the data, which is why this has to live with the workload.

**Then compare with the table next to you.** Different shape, same four rules.

```
 ? WHY THIS MATTERS

   You just proved the contract generalises, rather than being told
   it does. That comparison IS the evidence.
```

## 5.3 · Teardown · 10 min

```bash
op teardown infra/workloads
```

```
 ✓ YOU SHOULD SEE   terraform destroy complete
 ✗ IF NOT           tell the facilitator. it costs money until it is gone.
```

**M5 output:** a verify contract for a workload you actually run.

---

# M6 · Game day

**75 minutes · LIVE + OFFLINE · WORKSHEET 5**

## 6.1 · Predict · 5 min · SCORED

From your M1 trust map, before anything runs:

```
 code       survives?   Y / N
 state      survives?   Y / N
 config     survives?   Y / N
 identity   survives?   Y / N
 BASELINE   survives?   Y / N
```

## 6.2 · Break it · 10 min

```bash
op incident infra/workloads
op backup   infra/workloads
```

```
 ✓ YOU SHOULD SEE   planted: 2 EICAR files, 14 .locked files, 1 note
                    BASELINE marker still present: yes
                    then a backup job, queueing 5-15 min. THIS IS NORMAL.
```

The compromise is now inside a recovery point. Every vendor signal is about to go green.

## 6.3 · Restore, and read what came back · 20 min

```bash
op restore infra/workloads
op gate    infra/workloads
```

```
 ✓ YOU SHOULD SEE

   FAIL: 14 encrypted (.locked) files present
   ●●●●✗·  RECOVERABLE  blocked at Scan
   HOLD  exit 1
```

**Score your prediction now.**

```
 ? WHY THIS MATTERS

   backup Completed. restore Completed. VM healthy. Every vendor
   signal GREEN. The recovery point was still poison.

   Caught by thirty lines of shell anyone in this room can read.
```

## 6.4 · Four recovery points · 25 min · WORKSHEET 5

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

**The one fact you do not have:** the first anomalous log entry is *"sometime last week"*. Retention on that host is 7 days and the earliest surviving entry is already abnormal. The incident may have started 3 days ago. Or 9.

**Choose a point. Justify it in one sentence, naming what you give up.**

```
 ? WHY THIS MATTERS

   The gate promotes exactly one point, and it is the one squarely
   inside the incident window. That is not a bug. It is a policy
   written for OUTAGES being asked a question about COMPROMISE:

     an RPO target assumes the only cost of an older point is
     LOST DATA. Under compromise, the freshest point is the most
     DANGEROUS one.

   And notice A. It is the only point anyone can be certain about,
   it costs 400 days of orders, and it is only certain because
   NOTHING WAS VERIFIED between it and last week.

   That gap is not bad luck. It is the drill nobody scheduled.
```

**→ SYNTHETIC RECOVERY** is shown here, if the room wants a point that is not in that list.

## 6.5 · Evidence · 15 min · WORKSHEET 5

```bash
cat evidence/incident/summary.json
python3 -m resops verify config/incident.yaml
```

```
 ✓ YOU SHOULD SEE   audit trail intact — hash chain verified
```

**→ REPORTING** — the console view beside the evidence bundle. Same run, human view and machine view.

Write the evidence outline: what would you show your leadership, your auditor, and your own team, and which of the three is hardest?

**M6 outputs:** a scored prediction · a justified decision · an evidence outline.

---

# Close

**15 minutes · WORKSHEET 6**

```
 1  Unseal worksheet 1. Write today's real number beside it.
 2  Your workload: the five pattern steps, one line each.
 3  ONE next action. Named. With a date.
      a runbook change · a platform default · an evidence improvement
```

```
 THE ADOPTION LADDER

 L1  SEE       resops gate, read-only. your real number.        day 1
 L2  DECLARE   verify.sh for ONE tier-1 workload. 20 lines.     week 1
 L3  PROVE     one scheduled drill. one attestation.            week 2
 L4  GATE      required check on that ONE workload. ratchet.    month 1
 L5  PUBLISH   resops metrics on a wall. % provably recoverable. quarter 1
```

L1 is read-only and physically cannot mutate your environment. There is a test enforcing that. It tells you your real position by Monday.

**In seven days you will get one question: did you run it against anything real?**

---

## What is honestly not solved

```
 the lab workload is a VM      the contract transfers, worked examples
                               for managed DB and buckets are not written
 restore-verify costs money    sampling plus a per-tier freshness bar is
                               a policy, not a cost model. we do not have one.
 the crosswalk is INDICATIVE   it supports a resilience programme.
                               it is not a formal attestation.
 nobody owns this by default   it spans three teams who mostly do not
                               talk about recovery together
```

Further reading: [RESOPS.md](RESOPS.md) the idea · [VERIFY.md](VERIFY.md) the contract · [README.md](README.md) running it.
