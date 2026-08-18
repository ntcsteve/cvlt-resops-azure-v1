# DevOps Meets ResOps

> **A hands-on workshop in Resilience Operations: running recovery the way
> you already run delivery.** Every command is copy-paste, every step shows
> the expected result, and every concept is proven on a live workload as
> you go.

**Level** 300-400 · **Duration** 2h facilitated, about 3h self-paced ·
**Audience** platform engineers, SREs, cloud architects, and the people who
fund them

---

## What is ResOps?

Resilience Operations is the operational discipline that unites security,
infrastructure, and operations teams around critical services, resilient
system design, and continuous validation, so an organization can withstand
disruption, recover within defined impact tolerances, and prove it with
evidence.

It is an operating model, not a product.

```
 Backup asks    do we have copies?
 DR asks        can we recover if the datacenter is down?
 ResOps asks    can we PROVE critical services recover, clean,
                within tolerance, on demand?
```

Each era bolted its answer onto the last: backup, then disaster recovery,
then cyber resilience, each arriving as a separate tool and a separate
team. ResOps replaces the bolted-on stack with one discipline, run the way
you already run delivery. This workshop is that discipline, in your hands,
in one afternoon.

## The one idea

```
 You gate on tests.
 You gate on security scans.
 You do not gate on recoverability.
```

You have taken a whole class of failure and moved it from *we find out in
production* to *we find out at the pull request*. Three times.

```
 SHIFTED LEFT ALREADY              STILL ON THE RIGHT
 tests       -> CI gate            recoverability -> a ticket,
 security    -> scanner gate                        after an outage
 infra       -> plan gate
 lint        -> merge blocker
```

Each time it was the same fight. Each time nobody argued after the first
year. This workshop is about the fourth one.

## The lab you are standing in

```
 PRODUCTION PLANE          RECOVERY PLANE            ISOLATED PLANE
 ┌───────────────┐         ┌────────────────────┐    ┌───────────────┐
 │ your VM       │ agent   │ AIR-GAP POOL       │    │ restored copy │
 │ no public IP  │──────▸  │ immutable copies   │──▸ │ verified from │
 │ no open ports │ snapshot│ service-held keys  │    │ the inside,   │
 └───────────────┘         └────────────────────┘    │ then deleted  │
        ▲                            ▲               └───────────────┘
   attacker ──✗── no path from the VM to the copies, ever
```

The production plane is an Azure VM running a live service, locked down
the way production should be: no public IP, no inbound rules, no
interactive access. All operations flow through managed control planes,
the Azure guest agent and the Commvault API, which is exactly how the
workshop's commands, and a real incident response, reach it.

Commvault protects that service into an air-gapped, immutable storage
pool: the recovery plane. Nothing running on the VM can reach that pool,
including anything an attacker plants there. Restore drills rebuild a copy
of the service in isolation, verify it from the inside, and remove it.

Three planes. Trust flows one way, and every verdict in this workshop
comes from the plane that cannot be lied to.

When a concept deserves the fuller story, look for the UNDER THE HOOD notes
as you go.

## What you will walk

```
 1  BUILD      stand up the service, protect it, climb the ladder
 2  PROVE      read the proof: the ladder, the gate, the contract
 3  BREAK      compromise it, and watch two controls catch it
 4  CHOOSE     pick a recovery point under pressure
 5  RE-PROVE   repair, then earn the green verdict back
 6  GATE IT    make recoverability a merge blocker
 7  OWN IT     write the argument you will actually use
```

```
 OFFLINE   no cloud, no token, instant, cannot fail
 LIVE      a real Azure VM and a real backup platform
```

In a facilitated session, chapters 1 and 5 are done for you before you
arrive and your workload is already at `VALIDATED`.

## Setup

Ten minutes of readiness, so the rest of the workshop is all signal. In a
facilitated session most of this is done for you.

### Prerequisites (self-paced)

```
 an Azure subscription      1 free vCPU in your region. The lab is one
                            small VM plus a short-lived restore copy.
 a Commvault tenant         API endpoint + access token, an Azure
                            hypervisor connection, a protection plan
                            backed by air-gapped immutable storage
 this repository            with config/workshop.yaml filled in: your
                            codename, subscription and plan ids
 terraform · python 3.11+   and the az CLI, logged in
```

### Before you start

```bash
cd ~/resops-cvlt-azure
source .venv/bin/activate
```

```
 ✓ YOU SHOULD SEE   the prompt change to (.venv)
 ✗ IF NOT           fix the venv before anything else; nothing below
                    works without it. In a room: ask.
```

**WORKSHEET 1. Write it down now and set it aside.** You come back to it at
the end, and the distance between your two answers is the only measurement
this workshop makes.

```
 1. What % of your production estate could you PROVE is recoverable?
 2. How would you prove it, to someone who did not believe you?
 3. How long would producing that proof take?
```

---

## Chapter 1 · Build · ~35 min · LIVE · SOLO

```
 DO      stand up a production service, protect it, and climb it to
         a proven recovery
 LEARN   the three planes, the one door into a sealed VM, where a
         backup actually lives, and what a drill really does
```

One `terraform apply` gives you a real service: a VM with no public IP, no
inbound rules, no way in. Everything you do to it from here travels through
doors you are about to meet, and every step prints what it did so you can
compare against the boxes below.

### Provision the service

```bash
terraform -chdir=infra/workloads apply -auto-approve
```

```
 ✓ YOU SHOULD SEE   Apply complete, then Outputs: including
                    resource_group = "resops-<your-codename>-rg"
                    and vm_name = "<your-codename>"
 ⏱ HOW LONG         2-4 minutes
 ✗ IF NOT           read the first error line. Quota and login are the
                    usual causes: az account show, then retry once.
```

```
 ? UNDER THE HOOD: THE ONLY DOOR
   The VM has no network path in, so commands travel through the Azure
   guest agent: a process inside the VM that Azure hands scripts to,
   with your subscription's credentials as the key. Every plant, every
   repair, and every drill verification in this workshop goes through
   that one door, and the door works even when the network story is
   hostile.
```

### Connect the platform

**The one manual step.** Open your Commvault Command Center and trigger
Azure discovery on the hypervisor connection, then wait for the Cloud
Discovery job to complete. About two minutes. This step is a decision, not
a workaround: discovery of new cloud resources is an operation the platform
keeps behind its own controls.

```bash
python3 -m resops.operator.op preflight infra/workloads
```

```
 ✓ YOU SHOULD SEE   five PASS lines, including
                    <your-codename> discovered (cloud-native inventory)
 ✗ IF NOT           a FAIL line names the fix. "not discovered" means
                    the discovery job has not finished; wait and re-run.
```

### The first recovery point

```bash
python3 -m resops.operator.op protect infra/workloads
```

```
 ✓ YOU SHOULD SEE   protected: group resops-<your-codename>-vg
                    with your VM's id beside it
```

```bash
python3 -m resops.operator.op backup infra/workloads
```

```
 ✓ YOU SHOULD SEE   a backup job, then  backup Completed
 ⏱ HOW LONG         about 2 minutes
 ✗ IF NOT           if it sits on "Waiting", that is the media agent
                    queue, not a failure. DO NOT KILL IT.
```

```
 ? UNDER THE HOOD: AIR GAP AND IMMUTABILITY
   The recovery point you just created landed in an air-gapped,
   immutable storage pool.

   Air-gapped here is logical, not a cable in a drawer. The pool lives
   in a separate security domain with its own credentials, held by the
   backup service, never by the VM. Malware that owns the machine, even
   as root, has no path to the copies. The service reaches in; nothing
   reaches back.

   Immutable means retention-locked: for the retention window, the
   copies cannot be altered or deleted by anyone. Ransomware's first
   professional move is destroying backups before revealing itself.
   This is the control that makes that move fail.

   The vault preserves every moment faithfully, including this one.
   Choosing which moment to trust is the discipline the rest of this
   workshop builds.
```

### Prove it restores

A recovery point exists. Nothing has proven it works. That proof is a
restore drill: rebuild a copy from the point, in isolation, and verify it
from the inside.

```bash
python3 -m resops.operator.op restore infra/workloads
```

```
 ✓ YOU SHOULD SEE   the restore job complete, a restored VM validated
                    in Azure, then the attester's verdict from inside
                    the copy, ending:
                    OK: code intact, baseline present, 3 customer
                    records, no encryption markers, write/read verified
                    and finally the restored VM tearing itself down
 ⏱ HOW LONG         about 5 minutes end to end
 ✗ IF NOT           a guest-agent-not-ready failure on a fresh restore
                    is transient: run it again. Any FAIL: line is the
                    attester doing its job; read it before retrying.
```

```
 ? UNDER THE HOOD: WHAT A DRILL RESTORE IS
   An out-of-place restore builds a NEW VM from the recovery point's
   disk: fresh machine, fresh identity, no connection to production.
   The attester runs inside that copy, writes its verdict, and the
   copy is deleted. Production never stops, never rolls back, and
   never meets the restored machine. That is why drills are safe to
   run on any schedule: the blast radius is one disposable VM.
```

```
 ✦ WHAT YOU JUST BUILT
   A sealed production service, a recovery point in a vault the
   service itself cannot touch, and a drill that proved the point
   restores clean. You did in twenty minutes what most estates have
   never done once: recovery, demonstrated.
```

## Chapter 2 · Prove · ~10 min · LIVE

```
 DO      read the ladder, the gate, and the contract that earned them
 LEARN   what a Service Resilience Indicator is, and what an
         attestation actually claims
```

Your workload stands at the top of its ladder. Before anything gets broken,
see what good looks like and where each claim comes from. This part is
deliberately calm: if yes is not boring, no will mean nothing.

### Read the ladder

```bash
python3 -m resops.operator.op status infra/workloads
```

```
 ✓ YOU SHOULD SEE   ●●●●●●  VALIDATED
                    six dots filled, and a reason beside every line
                    discover names your group: 'resops-<your-codename>-vg'
 ✗ IF NOT           re-run the climb from chapter 1. In a room: tell
                    the facilitator your codename: <your-codename>.
                    Do not debug it.
```

Every line of that output pairs a recovery fact with a DevOps practice you
already run: discovery like service discovery, protection like GitOps
drift, detection like health checks, recovery like rollback readiness,
verification like scanning an artifact before deploy.

### The bar it passed

```bash
python3 -m resops.operator.op gate infra/workloads
```

```
 ✓ YOU SHOULD SEE   PROMOTE  recoverability proven · exit 0
 ✗ IF NOT           if it says HOLD and names coverage, a backup ran
                    after your last drill. Run the drill again and
                    re-gate, or keep reading. You will meet that exact
                    behaviour, on purpose, in the next chapter.
```

Now look at the bar it passed. It is not one threshold, it is a per-tier
one:

```bash
cat config/tiers.yaml
```

```
 ✓ YOU SHOULD SEE   tier1 and tier2, each declaring rpo_hours,
                    rto_minutes and attestation_max_age_days
```

```
 ? WHY THIS MATTERS
   A measurable, testable target per critical service is a Service
   Resilience Indicator. Read the NOTE at the bottom of that file:
   nobody restore-verifies everything every day, so the policy is not
   "everything is verified", it is "for THIS tier, something must have
   opened a recovery point and read it within N days".

   A tier that declares no freshness value is never checked for it.
   That is a legitimate choice, made explicitly, and still recorded.
```

### The contract that earned it

Then read what actually produced the verdict:

```bash
grep -A 80 'path: /opt/app/verify.sh' infra/modules/azure-vm/cloud-init.yaml
```

```
 ✓ YOU SHOULD SEE   about seventy lines of shell. Five checks.
                    the last one WRITES a record and reads it back, and
                    the script ends at  exit 0  (the start of the next
                    file in the listing may show below it)
```

```
 ? WHY YOU READ IT HERE AND NOT OVER SSH
   That VM has no public IP, no inbound rule, no open ports. You cannot
   reach it and neither can anything else. The only way in is the guest
   agent, which is exactly how the drill runs this script INSIDE the
   restored copy.

   The workload being unreachable is the point. The attester still ran.
```

Four of the five checks ask *is the right data here?*. The fifth asks *does
the store still work?*, which none of the others can answer. A read-only
mount passes the first four and fails a real service on its first write.

```
 ? UNDER THE HOOD: WHAT THE DRILL WRITES
   When a restore drill runs that script inside a restored copy, the
   verdict line gets captured into an attestation file: which recovery
   point, what was checked, what it said, when. The gate reads that
   file. It is evidence, not a flag somebody set, and its history is
   hash-chained so a rewritten past shows as a broken chain. You will
   watch this file lose its power in about ten minutes.
```

```
 ✦ WHAT YOU JUST READ
   A proven ladder, a per-tier bar, and a twenty-line contract owned
   by the people who know what "good" means for this service. Every
   claim traced to something you could open and read.
```

## Chapter 3 · Break · ~15 min · LIVE

```
 DO      compromise the workload you built, then watch two controls
         catch it two different ways
 LEARN   why proof does not accumulate, and where a verdict can
         honestly come from
```

You have a proven workload and a gate that says yes. Now break it. On
purpose, with something harmless and detectable.

But first, sit with this question, because the whole chapter turns on it:

```
                    Recoverable to WHAT?
```

You proved this workload is recoverable. Which recovery point is that
claim about? Hold your answer. The tools are about to give you theirs.

### Plant the compromise

```bash
python3 -m resops.operator.op incident infra/workloads
```

```
 ✓ YOU SHOULD SEE   incident: planting a detectable compromise in
                    <your-codename> (resops-<your-codename>-rg)
                    planted: 2 EICAR files, 14 .locked files, 1 note
                    BASELINE marker still present: yes
 ✗ IF NOT           check the VM is running: the guest agent needs
                    about 2 minutes after boot. Retry once, then stop.
```

EICAR is a 68-character test string the antivirus industry standardized in
the 1990s: every scanner on earth agrees to detect it as if it were
malware, precisely so people can test detection without handling anything
dangerous. The `.locked` files are high-entropy junk wearing ransomware's
naming pattern. Nothing here is armed; everything here is detectable. That
is the point: we need the alarms to be real, not the fire.

### Commit it into a recovery point

```bash
python3 -m resops.operator.op backup infra/workloads
```

```
 ✓ YOU SHOULD SEE   a backup job, then  backup Completed
 ⏱ HOW LONG         about 2 minutes
 ✗ IF NOT           if it sits on "Waiting", that is the media agent
                    queue, not a failure. DO NOT KILL IT.
```

```
 ? WHAT YOU ARE WATCHING
   Your own planted compromise being committed into a recovery point.
   The job says Completed. It is green. It is correct. Nothing is
   broken, which is exactly what makes it dangerous.

   The recovery point lands in air-gapped, immutable storage; nothing
   on the VM, including your compromise, can reach it.
```

```
 ? UNDER THE HOOD: WHAT A RECOVERY POINT IS
   One frozen moment of the disk, copied out whole. It does not
   accumulate, it does not update, and it does not know what happened
   after it. Keep that in mind for the next command.
```

### The gate answers twice

```bash
python3 -m resops.operator.op gate infra/workloads
```

```
 ✓ YOU SHOULD SEE   HOLD · exit 1
                    ↳ attestation does not cover the newest recovery point
```

```
 ? WHY THIS MATTERS, AND NOBODY PREDICTS THIS ONE

   You did not change the verdict. You took a BACKUP.

   An attestation is a claim about ONE recovery point, not a property
   of the workload. There is now a newer point and nothing has opened
   it, so the proof you had ten minutes ago vouches for nothing. Most
   people expect proof to accumulate. It does not.

   The distance between what you think you can recover and what you
   can prove is your RESILIENCE GAP. You just measured yours, in one
   line.
```

Now ask the threat lane what it thinks:

```bash
python3 -m resops.operator.op threatscan infra/workloads
```

```
 ✓ YOU SHOULD SEE   THREATS DETECTED · exit 1
                    the scan ran, and this recovery point is NOT safe
 ✗ IF NOT           if it stops asking for scan_plan_id, set it in
                    config/workshop.yaml and re-run. The first lesson
                    above already landed either way.
```

```
 ? WHERE THE SCAN RAN
   Not on the VM. ThreatScan opened the backup copy in the recovery
   plane and read it there; production was never touched. A verdict
   about a recovery point can only honestly come from the copy itself,
   and the copy lives where nothing from the VM can reach it.
```

```
 ? WHY THIS MATTERS
   Two HOLDs, two different reasons. The first said "nothing has looked
   at this point". The second said "something looked, and found
   malware". Those are opposite situations and they must never read the
   same. A check that examined nothing must never report a pass.
```

**Where you are now.** Your backup job said Completed. The restore said
Completed. The VM is healthy. Every signal the backup platform gave you was
green, and the recovery point you would have restored from is poison.

```
 ✦ WHAT YOU JUST PROVED
   A green pipeline committed a compromise into an immutable vault,
   and the gate caught it twice: once because proof went stale, once
   because something looked inside. Green is a job status, not a
   verdict about your data.
```

## Chapter 4 · Choose · ~15 min · OFFLINE

```
 DO      put your workload back, then pick a recovery point under the
         conditions that actually matter
 LEARN   why outage policy answers the wrong question under
         compromise, and the number that measures the right one
```

### Put it back

First, put your own workload back. This runs while you do the exercise.

```bash
python3 -m resops.operator.op remediate infra/workloads
```

```
 ✓ YOU SHOULD SEE   it removes exactly what the incident planted,
                    restores exactly what it took, then re-runs
                    verify.sh — the last line starts  OK:
 ✗ IF NOT           it raises rather than reporting success. Read what
                    it raised before touching anything; do not run it
                    twice blindly.
```

```
 ? WHAT REMEDIATE ACTUALLY DOES
   It removes exactly what the incident planted, restores the two
   files it stashed, and re-runs the attester. Surgical, because our
   incident recorded what it changed. The discipline for incidents
   that keep no manifest is exactly what comes next: choosing recovery
   points on evidence.
```

### Four recovery points, one decision

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

   AGGREGATE  HOLD — C-32-hours-ago, B-6-days-ago, A-400-days-ago · exit 1
```

**The fact you do not have:** the first anomalous log entry is *"sometime
last week"*. Retention is seven days and the earliest surviving entry is
already abnormal. It may have started three days ago. Or nine.

**Choose one. Justify it in a sentence, naming what you give up.**

```
 ? WHY THIS MATTERS

   The gate promotes exactly one point, and it is the one squarely
   inside the incident window. That is not a bug. It is a policy
   written for OUTAGES answering a question about COMPROMISE.

   An RPO target assumes the only cost of an older point is LOST DATA.
   Under compromise, the freshest point is the most DANGEROUS one.

   And look at A. The only point anyone can be certain about costs 400
   days of orders, and it is only certain because NOTHING WAS VERIFIED
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

```
 ✦ WHAT YOU JUST DECIDED
   Recovery under compromise is a decision, made by a human, on
   evidence, against a clock. The tools narrow the choice; they do not
   make it. MTCR measures how fast your organisation can make it well.
```

## Chapter 5 · Re-prove · ~20 min · LIVE · SOLO

```
 DO      close the loop: take a clean point, scan it, drill it, and
         earn the green verdict back
 LEARN   what actually restores trust after an incident, and what
         does not
```

Your VM is clean, but the gate still holds: the newest recovery point
still contains the compromise, and cleaning production changes nothing
inside an immutable vault. Trust is re-earned the same way it was earned
the first time.

### A clean point

```bash
python3 -m resops.operator.op backup infra/workloads
```

```
 ✓ YOU SHOULD SEE   backup Completed — a new point, from the clean VM
 ⏱ HOW LONG         about 2 min
```

### Scan it

```bash
python3 -m resops.operator.op threatscan infra/workloads
```

```
 ✓ YOU SHOULD SEE   no threat recorded for this workload — and the
                    output says plainly that this is NOT the same as
                    clean, and does not clear the Scan rung on its own
```

```
 ? WHY THIS MATTERS
   The scanner found nothing, and the tool refuses to call that clean.
   Absence of evidence is never a pass. What clears the Scan rung is
   the drill: something must OPEN the point and verify it from the
   inside.
```

### Prove it

```bash
python3 -m resops.operator.op restore infra/workloads
```

```
 ✓ YOU SHOULD SEE   the drill verdict, ending
                    OK: ... write/read verified
 ⏱ HOW LONG         about 5 minutes
```

```bash
python3 -m resops.operator.op gate infra/workloads
```

```
 ✓ YOU SHOULD SEE   ●●●●●●  VALIDATED
                    PROMOTE  recoverability proven · exit 0
```

```
 ✦ WHAT YOU JUST CLOSED
   Incident to trusted recovery, end to end: repair, clean point,
   scan, drill, gate. The verdict came back green because you
   re-proved it, not because time passed or a dashboard said so.
```

## Chapter 6 · Gate it · ~12 min · OFFLINE

```
 DO      run the gate across an estate, publish its numbers, and read
         the CI file that makes it a merge blocker
 LEARN   how a check survives contact with a real estate: the ratchet,
         and who owns what
```

One workload proving itself is a demo. The discipline starts when the same
gate runs across everything, on every pull request, publishing numbers
somebody has to look at.

### The estate

```bash
python3 -m resops gate config/estate.yaml
```

```
 ✓ YOU SHOULD SEE   six workloads, five of them HOLD, and a final line
                    AGGREGATE  HOLD — checkout-api, identity-svc,
                                      reporting-db, edge-cache, legacy-batch
                    exit 1
```

**Stop on `checkout-api` and `identity-svc`.** Same rung. Opposite reasons.
One was tested and is contaminated; one was never tested at all. The rung
hides that. The blocked stage names it.

### Publish the numbers

```bash
python3 -m resops metrics config/estate.yaml
```

```
 ✓ YOU SHOULD SEE   Prometheus text: resops_rung, resops_promotable,
                    resops_tolerated
 ✗ IF NOT           "no run to publish" means you skipped the gate
                    command above. Run it first; metrics publishes the
                    LAST run.
```

### The merge blocker

```bash
cat .github/workflows/resops-gate.yml
```

```
 ✓ YOU SHOULD SEE   about sixty lines. on pull_request, and daily.
```

```
 ? UNDER THE HOOD: WHY CI CAN TRUST THIS
   The gate is a pure function: read the facts, apply the tier's
   policy from tiers.yaml, exit 0 or 1. No clock games, no retries, no
   state of its own. That is the entire integration surface, and it is
   why the workflow file you just read is short: CI already speaks
   exit codes fluently.
```

```
 ? THE OBJECTION THIS ANSWERS
   Point this at a real estate and almost everything HOLDs on day one.
   Correctly. But then nobody can ship, so the check gets deleted by
   Friday.

   So a workload can declare a DATED tolerance:

       enforce_from: 2027-01-01
       tolerance_reason: "backup policy rebuild in flight"

   It still HOLDs, on screen and in the report. Only the aggregate
   stops counting it, and only until that date. A DATE, not a flag; a
   flag is permanent the moment somebody forgets it. And
   resops_tolerated publishes how many you have, so it is a number
   that has to go down.
```

```
 WHO OWNS WHAT, the argument you will have when you get back

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

```
 ✦ WHAT YOU JUST WIRED
   The fourth gate, shaped exactly like the other three: a required
   check, an honest number, and a ratchet that lets an estate adopt it
   without stopping the ships.
```

## Chapter 7 · Own it · ~30 min

```
 DO      write the argument you will actually face, and your answer
         to it
 LEARN   nothing new. This is where you find out what stuck.
```

### Write the argument

You will have this argument within a month, in a design review or a budget
meeting. Have it now, on paper, while the evidence is still under your
fingers.

```
 05 min   Write the three objections your staff engineer will raise.
          No answers yet. Just collect them, honestly.

 15 min   Answer each one in writing. Then read the ammunition below
          and steal anything better than what you wrote.

 05 min   Keep the ONE objection you will actually face, and your
          answer. That page is what you take home.
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
 ? WHY THIS AND NOT A SUMMARY
   An argument you have never made does not survive a design review.
   Writing it down, against real objections, is the difference between
   having attended a workshop and owning one.
```

### Your number, revisited

Now go back to your worksheet from the start. Read your three answers as if
a colleague wrote them.

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
 4  the workload's group. `resops list` finds it by name
```

L1 is read-only and **physically cannot mutate your environment.** The
engine makes no create, update or delete calls of any kind, and a test in
the suite fails if anyone adds one. That is the point of starting there: it
costs an afternoon and risks nothing.

**One next action. Named workload. Dated. Owner.** Not three.

```
 In seven days there is one question: did you run it against anything real?
```

```
 ✦ WHAT YOU OWN NOW
   A number you measured, an argument you wrote, and a first step that
   costs an afternoon and risks nothing.
```

---

## Wrap-up

### The model you just walked

```
 01 RESILIENCE GOVERNANCE          the tier bar you read in tiers.yaml:
                                   a Service Resilience Indicator,
                                   declared and testable
 02 RECOVERY PLANNING              choosing recovery points on
                                   evidence, not hope
 03 RECOVERY ARCHITECTURE          the three planes: air gap,
                                   immutability, isolated drills
 04 RESILIENCE THROUGH REPETITION  the drill, on a schedule; chapter
                                   5's whole argument
 05 MEASURING RESILIENCE           MTCR and the resilience gap, on a
                                   wall somebody has to look at
```

Capability answers "could we?". Outcomes answer "did we, and can we prove
it?". ResOps measures outcomes.

### The four terms you earned

```
 ResOps           recovery run as an operating discipline, the way you
                  already run delivery
 SRI              a measurable, testable resilience bar, per tier
 resilience gap   the distance between what you think you can recover
                  and what you can prove
 MTCR             mean time to CLEAN recovery. The word clean is the
                  entire argument.
```

### Your first step

L1 costs one afternoon and touches nothing. Run `resops gate` against one
workload you own, this week, and read your real number. Heroism cannot
scale; a discipline can, and it starts with one honest measurement. In
seven days there is one question: did you run it against anything real?
