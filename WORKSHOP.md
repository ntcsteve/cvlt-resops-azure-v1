# Trusted Recovery for Cloud-Native Workloads

> **Participant guide.** Work at your own pace. The facilitator floats.
> Every command is copy-paste. You should never type a path from memory.

**Level** 300-400 · **Duration** 6h35m door to door · **Audience** platform engineers, SREs, cloud architects

Worksheets: [WORKSHEETS.md](WORKSHEETS.md). Delivering this? There is a facilitator runbook – prep, timings, break-glass and what not to claim. It is shared directly rather than published; ask whoever owns the workshop.

**This is the six-hour day, and it is a separate artifact from the two-hour one.** [WORKSHOP-2H.md](WORKSHOP-2H.md) aims at conviction and is built into a participant HTML by `tools/guide/`; this document aims at capability, is read as markdown, and carries three exercises the short day has no room for: the trust map, verify-your-verifier, and writing an attester for a workload shape you actually run. The two share a subject and deliberately not a structure. Do not expect them to match.

---

## The one idea

```
 You gate on tests.
 You gate on security scans.
 You do not gate on recoverability.
```

If you leave with nothing else, leave with the question it implies: *how much of your estate could you prove is recoverable right now, to someone who did not believe you?*

## The map of the day

Recovering a service you can no longer trust is five decisions. **You are not going to learn them and then apply them. You are going to walk them, and write them down at the close for a workload you own.**

```
 1  what do I still trust?                    M1
 2  which copies survived the blast radius?   M1  → air gap
 3  which recovery points are clean?          M4  → verify.sh
 4  which one do I pick?                      M5  → four points
 5  how do I justify it afterwards?           M5  → evidence
```

## How it runs

```
 M1  Broken trust                60m   what can you still trust?
 M2  Recoverability as code      50m   the check, and how it scales
 M3  Verify your verifier        30m   the most transferable 30 minutes
 M4  Lab – declare and prove     75m   you write an attester
 M5  Game day                    75m   break it, then choose
     Close                       20m
```

```
 OFFLINE   no cloud, no token, one second, cannot fail
 LIVE      a real Azure VM, already provisioned for you
```

Your workload was climbed to VALIDATED before you arrived. You will not spend the morning on terraform.

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

# M1 · Recovery Under Broken Trust

**60 minutes · OFFLINE**

**Objective:** a service can be fully available and still be operationally untrusted. Produce the trust map you get scored against in M5.

## 1.1 · See the gap · 10 min

```bash
python3 -m resops gate config/estate.yaml
```

```
 ✓ YOU SHOULD SEE   six workloads, each rendered like this –

   ▸ payments-api  prod  payments  (critical)
     ●●●●●●  VALIDATED  ·  RPO 3.0h
     ↳ recovery proven – job 884730
     PROMOTE  recoverability proven · exit 0

   ▸ checkout-api  prod  payments  (critical)
     ●●●●✗·  RECOVERABLE  ·  RPO 4.0h  blocked at Scan
     ↳ recovery point failed restore-verify – 14 encrypted (.locked) files present
     HOLD  ... · exit 1

   – and four more blocked at Validate, Detect, Recover and Discover,
   then a final line:

   AGGREGATE  HOLD – checkout-api, identity-svc, reporting-db,
                     edge-cache, legacy-batch · exit 1

 ✗ IF NOT   `pip install -e .` then try again.
```

The **bar** is the six stages. The **state** is where you stopped. **blocked at** names the stage that did not clear.

**Stop on `checkout-api`.** Protected. Backups completing. SLA met. Recovery *proven* by a real restore. Every light green, and it still must not ship.

```
 ? WHY THIS MATTERS

   Available is not the same as trusted. Every other row is a
   problem you already know how to describe. That one is not.

   checkout-api and identity-svc sit on the SAME rung for opposite
   reasons – one was tested and is contaminated, one was never
   tested. The rung hides that. The blocked stage names it.
```

## 1.2 · Your number · 5 min · WORKSHEET 1

Write it. Fold it. Hand it in. You get it back at the close.

```
 1. What % of your production estate could you PROVE is recoverable?
 2. How would you prove it, to someone who did not believe you?
 3. How long would producing that proof take?
```

```
 ? WHY THIS MATTERS
   The only measurement the day makes. If your answer at the close
   is the same as now, we wasted your time and I want to know.
```

## 1.3 · Trust map · 35 min · WORKSHEET 2

### The scenario

`orders-api` is a tier-1 payments service. 41,892 customer records.

A deployment landed Tuesday. A storage credential with broad access was over-permissioned and used from an address nobody recognizes. This morning there is a `README_RECOVER.txt` in the data directory.

The service is still responding. Dashboards are green.

### The four categories

Every workload, at any size, is made of four things. Yours has forty services and six managed stores. Still these four, just more of each.

```
 CODE       what executes            did this come from the pipeline?
 STATE      what it has written      it changed after the deploy. expected?
 CONFIG     what shapes behavior    who can write this?
 IDENTITY   what it can reach with   this is the blast radius
```

In today's lab:

```
 CODE      /opt/app/serve.sh · /opt/app/VERSION
 STATE     /var/lib/app/data/  (customers.csv · orders.ndjson · BASELINE)
 CONFIG    /etc/app/config.yml       world-readable, on purpose
 IDENTITY  /etc/app/creds.env        the storage key
```

### The exercise

Mark each. Justify in one line.

```
 TRUSTED     I would run production on this as-is, and here is why
 UNTRUSTED   I have positive reason to doubt it
 UNKNOWN     I have no evidence either way
```

Then:

```
 4. What single missing fact would move the most boxes out of UNKNOWN?
 5. Your backups. Trusted, untrusted or unknown – and why?
```

```
 ? WHY THIS MATTERS
   UNKNOWN is the honest answer more often than people write. A box
   you cannot justify is worth more today than a confident one.

   KEEP THIS SHEET. In M5 you find out which boxes you got right,
   and it is scored.
```

## 1.4 · Your backups · 10 min

Most tables write **unknown** at question 5. So:

```
 The credential that was misused – could it reach your backups?
 Could it delete them? Could it change their retention?
 Who would know if it had?
```

**→ AIR GAP PROTECT** is shown here, in the console, as the answer to the question you just wrote down yourself. An isolated, immutable copy the compromised credential cannot reach.

```
 ? WHY THIS MATTERS

     the console DECLARES it     an air-gapped, immutable pool
     the code VERIFIES it        the Protect stage confirms the plan
                                 is attached, on every run

   A control you declared and never verified is a control you
   hope you have. Hold that thought – M2 explains why some things
   belong in a console and some never do.
```

**M1 outputs:** a sealed number · a trust map · pattern steps 1 and 2, walked.

---

# M2 · Recoverability as Code

**50 minutes · OFFLINE**

**Objective:** build the layer that is missing from almost every estate.

## 2.1 · Build, run, incident · 10 min

Three modes. You already live all three.

```
 BUILD      decided once, deliberately, a human on the hook
            design review · terraform written · policy agreed
            → UI or code. either. it is architecture.

 RUN        what must be true on every change, forever
            CI · reconcile · gate · alert · publish
            → CODE ONLY. a human clicking here IS the drift.

 INCIDENT   rare, urgent, incomplete information, judgement
            console · dashboards · correlate · decide · defend
            → UI. code is too rigid for a question nobody anticipated.
```

**The test for any task:** does the answer change per workload or per run?

```
 changes every run     → automate. a human cannot keep up.
 decided once          → UI. a human SHOULD be on the hook.
 your API says no      → document it, prep it, stop fighting it.
```

```
 ? WHY THIS MATTERS

   MOST BACKUP TOOLING GIVES YOU
     BUILD      someone configured it, once, years ago
     RUN        ─────── nothing ───────
     INCIDENT   someone clicks restore, in a panic

   That missing middle is the only place recoverability is proven
   or lost. Green backup dashboards are a BUILD artefact being read
   as a RUN signal. "We have backups" is a build claim.
   "We can recover" is a run claim.

   RELIABILITY, PRE-SRE          RECOVERABILITY, TODAY
   HA architecture               backup policy configured
   ─── nothing ───               ─── nothing ───
   heroics and war rooms         panic restore

   SRE invented the run layer: SLOs, error budgets, required checks.
   Recoverability is where reliability was before SRE existed.
   The next 40 minutes build that layer.
```

## 2.2 · Read the bar · 5 min

Which stage failed, and what is the fix?

```
 A   ●●●✗··   MONITORED        C   ✗·····   UNDISCOVERED
 B   ●●●●●✗   RECOVERABLE      D   ●●●●✗·   RECOVERABLE
```

```
 ✓ ANSWERS
   A  Recover   backups green, RPO/SLA bar missed
   B  Validate  recoverable on paper, never proven by a restore
   C  Discover  nobody onboarded it
   D  Scan      the point you would restore from is not trusted

   B and D are the same rung, different problems.
```

## 2.3 · The ratchet · 15 min

Point this at a real estate and almost everything HOLDs on day one. Correctly. But nobody can ship, so the check gets deleted by Friday.

Open `config/estate.yaml`, find `reporting-db`, uncomment:

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
   ↳ TOLERATED until 2027-01-01 – still a HOLD, excluded from the
     aggregate until that date

   AGGREGATE  HOLD – checkout-api, identity-svc, edge-cache,
                     legacy-batch · 1 TOLERATED (reporting-db) · exit 1

 ✗ IF NOT   exit 2 means a malformed date. it must be YYYY-MM-DD.
```

Put it back:

```bash
git checkout config/estate.yaml
```

```
 ? WHY THIS MATTERS
   reporting-db STILL HOLDS. On screen, in the bundle, in the report.
   Only the aggregate stopped counting it, and only until that date.

   A bypass hides a gap. This declares one, counts it, and expires
   by itself. A date, not a flag – a flag is permanent the moment
   someone forgets it.

   The count publishes as resops_tolerated, so "we have 3 unenforced"
   becomes a number on a wall that has to go down.
```

## 2.4 · Twenty lines of CI · 10 min

```bash
cat .github/workflows/resops-gate.yml
python3 -m resops metrics config/estate.yaml
```

```
 ✓ YOU SHOULD SEE   a workflow on pull_request + daily, then Prometheus
                    text with resops_rung, resops_promotable,
                    resops_tolerated

 ? WHY THIS MATTERS
   Judge once, publish many. No tenant, no network, no agent on any
   workload. This is the "% provably recoverable" number nobody has.
```

## 2.5 · Making it the default · 10 min

Discussion. No commands.

```
 "HOW DOES THIS BECOME A DEFAULT FOR 200 SERVICES?"
   infra/platform/    the paved road. built once, by platform.
   config/tiers.yaml  THE policy. RPO, RTO, attestation freshness.
   an app team        declares `tier: tier1` and inherits every bar.
   → they do not configure recoverability. they choose a tier.

 "DO I WRITE 200 verify.sh FILES?"
   No. One per workload SHAPE. VM, managed DB, bucket, queue.
   Most teams have five shapes and think they have two hundred.

 "DOES THIS PAGE ME?"
   NO. Recoverability drift is not an incident. It is a MERGE
   BLOCKER. It fails a pull request. It does not wake you up.
```

```
 WHO OWNS WHAT – the argument you will have when you get back

   verify.sh    the app team      only they know what "good" is
   the drill    platform          it is infrastructure
   the gate     CI                it is a required check
   tiers.yaml   platform + risk   it is policy
```

**M2 outputs:** a gate config you edited · the ownership split · a rule that transfers to every tool you own.

---

# M3 · Verify Your Verifier

**30 minutes · WORKSHEET 3**

**Objective:** the most transferable thirty minutes of the day, and it is not about backup.

## 3.1 · Ship or hold? · 20 min

A real recovery point, from a real tenant. This is what you would be restoring from.

```
 backup       Completed
 anomalies    none recorded
 verdict      ?
```

**Vote. Out loud, hands up, before anything else is said.**

Then open the recovery point yourself and find the field nobody reads –
`threatStatsForRecovery`:

```
 totalFiles          ?
 totalCleanFiles     ?
 maliciousFiles      ?
```

Compare it against a point that *was* scanned:

```
 SCANNED        totalFiles 68398 · totalCleanFiles 68396 · maliciousFiles 2
 NEVER SCANNED  threatStatsForRecovery = { "latestTAJobTime": 0 }
                the object is THERE. the counts are not.
```

**`latestTAJobTime: 0` is the signal.** Not a missing object, not a zero count. A
timestamp of zero, meaning no threat analysis has ever run against this point.
Measured on our own workload: **19 recovery points, every one of them `0`.**

```
 ⚠ THE SCANNED EXAMPLE IS FROM A DIFFERENT VM GROUP.
   Threat scan populates Client/Anomaly for our workload, and it works – it
   found the 2 planted files. It has never populated threatStatsForRecovery
   for us. So you can reproduce the LEFT column on your own workload, and
   the right-hand counts only on the one group in this tenant that ever
   received File Indexing jobs. Do not go looking for 68398 on your VM.
```

```
 ? THE RULE THIS PRODUCES
   Absence of evidence is not evidence of absence.
   A check that ran nothing must never report a pass.

   "no anomalies recorded" did not mean clean.
   It meant NOTHING HAD LOOKED.
```

**And the other half, from the same tenant on the same day.** The scan that *did*
run found the 2 planted EICAR files and reported `encryptedFiles: 0` on a recovery
point holding **14 encrypted ones**. Our own thirty-line `verify.sh` found those 14
and never saw the EICAR.

```
 threat scan   found the 2 EICAR       missed the 14 encrypted
 verify.sh     found the 14 encrypted  missed the 2 EICAR
```

Neither is sufficient alone. That is why both exist, and why a negative from either
one blocks.

You will then be shown the two places that rule is enforced in code, rather than asserted on a slide.

## 3.2 · Three checks in your pipeline · 10 min · WORKSHEET 3

```
 Name three checks in YOUR pipeline that could pass having
 examined nothing.
```

Starters:

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
   did the metric stop being emitted? Every SRE here has that scar.
   This lesson is not about backup at all.
```

**M3 output:** three checks you will go and verify.

---

# M4 · Lab – Declare and Prove

**75 minutes · LIVE · WORKSHEET 4**

**Objective:** author an attester. The one thing nobody can write for you. This is pattern step 3.

## 4.1 · Your workload · 20 min

Climbed to VALIDATED before you arrived.

```bash
op gate infra/workloads
```

```
 ✓ YOU SHOULD SEE   ●●●●●●  VALIDATED
                    PROMOTE  recoverability proven · exit 0
 ✗ IF NOT           tell the facilitator your codename. do not debug it.
```

Now read what produced that verdict:

```bash
grep -A 80 'path: /opt/app/verify.sh' infra/modules/azure-vm/cloud-init.yaml
```

```
 ? WHY YOU READ IT HERE AND NOT OVER SSH
   That VM has no public IP, no inbound NSG rule, no open ports.
   You cannot reach it and neither can anything else. The only way
   in is the guest agent – which is exactly how the drill runs this
   script inside the RESTORED copy.

   The workload being unreachable is the point. The attester still
   ran, inside a machine nobody could log into.
```

About seventy lines. Five checks. Full contract in [VERIFY.md](VERIFY.md).

## 4.2 · Write a check for YOUR shape · 45 min · WORKSHEET 4

**Pick the shape you actually run.** Not the one in the lab.

```
 VM               bash, runs inside the restored copy
 MANAGED DB       restore to a temp instance, run SQL
 OBJECT STORAGE   restore to a temp bucket, checksum + schema probe
 KUBERNETES       restore, apply, probe
```

Pseudocode counts. Four rules, none language-specific:

```
 1  the verdict LINE is authoritative      OK: / FAIL:
 2  ONE line per message                   the parser stops at the first
 3  print the verdict LAST                 then exit
 4  no verdict means UNATTESTED            never clean
```

Aim left, not right:

```
 GOOD                                WEAK
 the file PARSES                     the file exists
 row counts in an expected range     the disk is the expected size
 a known-good marker is present      the timestamp looks recent
 schema is what you expect           the service starts
```

The right column is what a backup product already tells you. The left requires opening the data.

**Then compare with the table next to you.**

```
 ? WHY THIS MATTERS
   You just proved the contract generalizes rather than being told
   it does. That comparison IS the evidence.
```

```
 ✗ DO NOT TEAR DOWN   your workload is needed in M5 – the game day
                      breaks and restores this same VM. you retire
                      it at the close, and not before.
```

**M4 output:** a verify contract for a workload you actually run.

---

# M5 · Game Day

**75 minutes · LIVE + OFFLINE · WORKSHEET 5**

Pattern steps 4 and 5. This is the first time today you are in incident mode.

## 5.1 · Predict · 5 min · SCORED

From your M1 trust map, before anything runs:

```
 code · state · config · identity · BASELINE      survives?  Y / N
```

## 5.2 · Break it · 10 min

```bash
op incident infra/workloads
op backup   infra/workloads
```

```
 ✓ YOU SHOULD SEE   planted: 2 EICAR files, 14 .locked files, 1 note
                    BASELINE marker still present: yes
                    then a full listing of the data directory

 ⏱ HOW LONG         op incident ~30s · op backup ~2 min
                    A backup CAN queue for a media agent slot. Measured
                    here: 77-149s across 23 runs, and one media agent
                    failover took 27 min. If it sits on "Waiting", that
                    is the queue.
                    DO NOT KILL IT.

 ✗ IF NOT           `op: command not found` means you skipped
                    `source .venv/bin/activate`. Go back to Before you start.
```

**Watch your backup job in the console while it queues.**

```
 ? WHAT YOU ARE WATCHING
   Your own planted compromise being committed into a recovery point.
   The job goes Completed. Green. Correct. Nothing is broken –
   which is exactly what makes it dangerous.
```

## 5.3 · Restore, and read what came back · 20 min

```bash
op restore infra/workloads
op gate    infra/workloads
```

```
 ⏸ IT WILL PAUSE    the drill restores your VM, checks it, then STOPS:

                      ✓ RECOVERED: <name>-restore is running in Azure
                        Press Enter to tear it down…

                    That is deliberate. Look at it in the portal first if
                    you want. It has no public IP, so there is nothing to
                    connect to, by design. Press Enter when you are done.

 ✓ YOU SHOULD SEE   from op restore –

   FAIL: 14 encrypted (.locked) files present

   === DRILL VERDICT ===
     job status : Completed
     azure VM   : PASS – exists & running
     attestation: FAIL – attestation failed

   RESTORE DRILL DID NOT PASS – the restored copy is not clean –
   verify.sh said so inside it.

                    then from op gate –

   ●●●●✗·  RECOVERABLE  blocked at Scan
   ↳ recovery point failed restore-verify – 14 encrypted (.locked) files present
   ↓ regressed VALIDATED→RECOVERABLE
   HOLD  exit 1
```

```
 ✗ IF NOT   op restore exiting NON-ZERO here is CORRECT – it is the drill
            refusing to certify a compromised copy, not a broken command.

            If the HOLD says "failed threatscan" instead of
            "failed restore-verify", you ran `op threatscan` at some point.
            A threat finding outranks the drill's own verdict, so you are
            seeing a different (also correct) refusal. The lesson survives;
            your output just will not match the box above.
```

**Score your prediction now.**

```
 ? WHY THIS MATTERS
   backup Completed. restore Completed. VM healthy. Every vendor
   signal GREEN. The recovery point was still poison.

   Caught by seventy lines of shell anyone here can read.
```

## 5.4 · Four recovery points · 25 min · WORKSHEET 5

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

**The fact you do not have:** the first anomalous log entry is *"sometime last week"*. Retention is 7 days and the earliest surviving entry is already abnormal. It may have started 3 days ago. Or 9.

**Choose. Justify in one sentence, naming what you give up.**

```
 ? WHY THIS MATTERS
   The gate promotes exactly one point, and it is the one squarely
   inside the incident window. That is not a bug. It is a policy
   written for OUTAGES answering a question about COMPROMISE:

     an RPO target assumes the only cost of an older point is
     LOST DATA. Under compromise, the freshest point is the
     most DANGEROUS one.

   And notice A. The only point anyone can be certain about, it
   costs 400 days of orders, and it is only certain because
   NOTHING WAS VERIFIED between it and last week.

   That gap is not bad luck. It is the drill nobody scheduled.
```

**→ SYNTHETIC RECOVERY** is named here, if the room wants a point that is not in that list.

## 5.5 · Evidence · 15 min · WORKSHEET 5

```bash
cat evidence/incident/summary.json
python3 -m resops verify config/incident.yaml
```

```
 ✓ YOU SHOULD SEE   audit trail intact – hash chain verified
```

**Pull a report in the console** and put it beside the bundle.

```
 ? WHY THIS MATTERS
   the console report   the operation ran        human-readable
   the evidence bundle  the decision was         machine-readable,
                        justified, and against   hash-chained
                        which control

   Neither replaces the other.
```

Write the evidence outline: what would you show leadership, an auditor, and your own team, and which is hardest?

**M5 outputs:** a scored prediction · a justified decision · an evidence outline.

---

# Close

**20 minutes · WORKSHEET 6**

**First, retire your workload.** It has done its job, and it costs money until it
is gone. Start this now – it runs while you write.

```bash
op teardown infra/workloads
```

```
 ✓ YOU SHOULD SEE   terraform destroy complete, before the close ends
 ✗ IF NOT           tell the facilitator BEFORE you leave. it cannot be
                    retired from anyone else's machine.
```

You have now walked all five steps. Write them down for something real.

```
 1  Unseal worksheet 1. Write today's number beside it.
 2  The five steps, for a workload YOU own. One line each.
 3  ONE next action. Named. Dated.
      a runbook change · a platform default · an evidence improvement
```

```
 THE ADOPTION LADDER
 L1  SEE       resops gate, read-only. your real number.       day 1
 L2  DECLARE   verify.sh for ONE tier-1 workload. 70 lines.    week 1
 L3  PROVE     one scheduled drill. one attestation.           week 2
 L4  GATE      required check on that ONE workload. ratchet.   month 1
 L5  PUBLISH   % provably recoverable, on a wall.              quarter 1
```

L1 is read-only and physically cannot mutate your environment. There is a test enforcing that.

**In seven days you get one question: did you run it against anything real?**

---

## What is honestly not solved

```
 the lab workload is a VM      the contract transfers; worked examples
                               for managed DB and buckets are not written
 restore-verify costs money    sampling plus a per-tier freshness bar is
                               a policy, not a cost model. we have none.
 the crosswalk is INDICATIVE   supports a resilience program.
                               not a formal attestation.
 nobody owns this by default   it spans three teams who mostly do not
                               talk about recovery together
```

Further reading: [RESOPS.md](RESOPS.md) the idea · [VERIFY.md](VERIFY.md) the contract · [README.md](README.md) running it.
