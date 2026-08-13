# Workshop - Resilience Operations on Azure and Commvault

> A hands-on workshop + toolkit - prove your Azure workloads are recoverable, and gate promotion on it, **the ResOps way.**

Your backups are green, but **when did you last actually recover from one?**

DevOps turned infrastructure, delivery, and reliability into reconciled, gated loops - provisioned as code, checked in CI, watched for drift. **Recoverability is the loop that's still run on faith.** Resilience Operations (ResOps) closes it with the playbook you already use: declare it as code, prove it with a drill, and gate promotion on the proof.

```
 resops   the readiness ladder + the promotion gate   READ-ONLY - reads and judges
 op       drive a workload up the ladder              WRITE - drives the climb
```

**This workshop, end to end:** a real Azure VM climbs from nothing to **VALIDATED** (recovery proven by an actual restore), the gate flips to **PROMOTE**, and you get a DORA/NIST/APRA evidence report. Then you **break trust on purpose** - plant a detectable compromise, back it up, and watch the same commands reach the opposite verdict, because a backup that completed successfully still isn't always safe to restore from. Then you tear it all down. **See it in 2 minutes** (no cloud), then the live workshop runs in three parts: **set up** (once, ~15 min), **onboard & climb** (~20 min), and **break trust** (~10 min).

## Quick start

Already have an Azure subscription, a Metallic tenant, and a filled `config/workshop.yaml`?

```bash
source .venv/bin/activate                    # pip install -e . if first time
resops gate  config/estate.yaml              # no cloud, no token — the whole idea in one second
op validate  infra/workloads                 # config + IAM + environment — fix blockers before touching anything
terraform -chdir=infra/workloads apply       # provision the VM
op climb     infra/workloads                 # protect → backup → restore + verify → VALIDATED
op gate      infra/workloads                 # PROMOTE / HOLD + DORA/NIST/APRA evidence report
op incident  infra/workloads                 # optional — break trust, then backup + restore → HOLD
op teardown  infra/workloads                 # always run this — the VM costs money until you do
```

New here? Start with [See it first](#see-it-first---one-command-no-cloud-no-token) below (zero setup), then follow [Part 1 — Set up](#part-1---set-up-once-15-min).

### Which document do you want?

Two different things live in this repo, and it's worth knowing which one you're reading.

```
 THE TOOLKIT — work through it yourself, at your own pace
   README.md        ← you are here. how do I run it?      Parts 1-3 below
   RESOPS.md        what is the idea, and why adopt it?
   VERIFY.md        how do I write the one file nobody can write for me?

 THE FACILITATED DAY — one room, 6.5 hours, five modules
   WORKSHOP.md      the participant guide                 M1-M5
   WORKSHEETS.md    six printable sheets
   (a facilitator runbook exists and is shared directly, not published —
    it carries delivery coaching and tenant-specific detail)
```

**Parts 1-3 in this file** are the solo walkthrough: provision, climb, break trust, tear down. **M1-M5 in [WORKSHOP.md](WORKSHOP.md)** are a facilitated day built on the same commands, with the setup done in advance so a room never touches terraform. They are not two versions of the same thing; pick the one that matches why you're here.

## See it first - one command, no cloud, no token

```bash
python3 -m resops config/demo.yaml
```
```
 ●●✗···  PROTECTED  blocked at Detect
   ✓ discover · ✓ protect · ✗ detect · · recover · · scan · · validate
```

**How to read it:** six dots = the six levels. This workload cleared Discover and Protect (●●), then stalled at Detect (✗) - its last backup wasn't clean, so it can't be trusted to recover. The level *is* the verdict. Canned reads - zero network or token; the same ladder, PROMOTE/HOLD gate, and DORA/NIST/APRA crosswalk a live run produces. Every level maps to something you already do for code.

### The whole estate - one command, one verdict

```bash
python3 -m resops gate config/estate.yaml
```
```
 ●●●●●●  VALIDATED     payments-api   recovery proven          PROMOTE
 ●●●●✗·  RECOVERABLE   checkout-api   restored copy came back dirty  HOLD
 ●●●●●✗  RECOVERABLE   identity-svc   recoverable, never proven      HOLD
 ●●✗···  PROTECTED     reporting-db   last backup failed             HOLD
 ●●●✗··  MONITORED     edge-cache     backups green, SLA missed      HOLD
 ✗·····  UNDISCOVERED  legacy-batch   nobody onboarded it            HOLD

 AGGREGATE  HOLD - checkout-api, identity-svc, reporting-db, edge-cache, legacy-batch · exit 1
```

Six workloads, six different blocking points, one aggregate verdict, one exit code your CI could gate on. Note `checkout-api` and `identity-svc` sit on the **same level** for **different reasons** - one was never tested, the other was tested and is contaminated. The level alone would hide that; the blocked stage names it. The gate HOLDs if **any** workload isn't VALIDATED - criticality is recorded as evidence, never a way to ship past a gap. Still zero network, still under a second, and it writes the same evidence bundle, report and hash-chained audit trail a live run does.

**Stop on `checkout-api`.** Every light is green - protected, backups completing, SLA met, and recovery *proven* by a real restore - and it still must not ship, because the point it would restore from carries a threat. **Available is not the same as trusted.** That single line is why the Scan level exists.

### Turning it on without everything going red

Point this at a real estate and almost everything HOLDs on day one. Correctly. But nobody can ship, so the check gets deleted by Friday - and the only tool that told you the truth is gone. You don't switch on 100% coverage enforcement against a legacy codebase either. You **ratchet**:

```yaml
  - name: reporting-db
    enforce_from: 2027-01-01                          # a DATE, not a flag
    tolerance_reason: "backup policy rebuild in flight"
```

```
 ●●✗···  PROTECTED  reporting-db  last backup failed        HOLD
 ↳ TOLERATED until 2027-01-01 - still a HOLD, excluded from the aggregate until that date

 AGGREGATE  PROMOTE - 5/6 enforced and clear · 1 TOLERATED (reporting-db) · exit 0
```

**This is not a bypass, and the difference is the whole point.** A bypass hides a gap. Here the workload's own verdict is untouched - it still prints HOLD, still names its blocked stage, still lands in the bundle and the report - and only the *aggregate exit code* stops counting it, because that's the only thing blocking a pipeline. The count is published as `resops_tolerated`, so **"we have 3 unenforced" is a number on a wall that has to go down.**

It's a date rather than a boolean on purpose: a flag is permanent the moment someone forgets it, a date expires on its own and the workload starts enforcing with no action from anyone. A typo fails the run (exit 2) rather than tolerating forever. Use it to adopt the gate. Don't use it to defer a gap you have no plan to close.

Two things worth trying on it:

```bash
# 1. REGRESSION - edit config/demo/validated.json, set "proof": null, re-run.
#    The trend flips to  ↓ regressed VALIDATED→RECOVERABLE  and the gate HOLDs.
python3 -m resops gate config/estate.yaml

# 2. TAMPER - hand-edit any line in evidence/estate/<workload>/history.jsonl.
#    The hash chain breaks and names the entry.
python3 -m resops verify config/estate.yaml     # TAMPERED - breaks at entry 0
```

### Put the estate on a wall

```bash
python3 -m resops gate    config/estate.yaml    # judge once…
python3 -m resops metrics config/estate.yaml    # …publish many
```
```
 resops_rung{workload="payments-api",criticality="critical"} 6
 resops_promotable{workload="payments-api"} 1
 resops_tolerated{workload="reporting-db"} 0     # 1 once you declare enforce_from
 resops_attestation_age_days{workload="identity-svc"} 47.0
 resops_workload_info{workload="checkout-api",state="RECOVERABLE",blocked_stage="Scan"} 1
 resops_control_coverage{framework="dora",control="Art. 11/12 (periodic testing…)",outcome="PASS"} 1
```

Reads `evidence/` from the last run - **no tenant, no network, no agent on any workload.** Pipe it at a Prometheus pushgateway from the same CI job that runs the gate, and a platform team can finally answer the question nobody can answer today: *how much of my estate is provably recoverable?*

The compliance rollup is the part auditors ask for and nobody has:

```
 DORA Art. 8   asset identification            5/6  ████████▁▁
 DORA Art. 12  backup policies                 5/6  ████████▁▁
 DORA Art. 10  detection of anomalies          4/6  ██████▁▁▁▁
 DORA Art. 12  restoration & recovery methods  3/6  █████▁▁▁▁▁
 DORA Art. 12  integrity before recovery       2/6  ███▁▁▁▁▁▁▁
 DORA Art. 11/12  periodic recovery testing    1/6  ██▁▁▁▁▁▁▁▁  ◀
```

Everyone can identify assets. Almost nobody can *prove* they tested recovery. **This is the only compliance view that gets less green the closer you look** - because it measures whether recovery was proven, not whether a policy exists. Cardinality is bounded by controls, not workloads, so it stays ~60 series at 6 workloads or 600. *(The mapping is indicative - it supports a resilience programme, not a formal attestation.)*

## The idea

A workload sits on **one level** of a readiness ladder; the level *is* the verdict. You climb by clearing each stage, and the gate ships only what's proven recoverable.

```
 UNDISCOVERED ─Discover─▸ DISCOVERED ─Protect─▸ PROTECTED ─Detect─▸ MONITORED
     ─Recover─▸ RECOVERABLE ─Scan─▸ TRUSTED ─Validate─▸ VALIDATED
```

It's **two reconciliation loops** - and you already run the first:

```
 Terraform reconciles INFRA          the resops ladder reconciles RECOVERABILITY
 "does the world match my config?"   "is it ACTUALLY recoverable, per my SLO?"
 → terraform plan shows config drift → the gate blocks promotion on recoverability drift
```

`resops` is read-only - share it, drop it in CI, it can't touch your environment. `op` is how you climb; in production the backup schedule does this for you and the gate just confirms it.

### What each stage maps to

Each stage is the step that lifts a workload onto the next level - and each is a practice you already run for code, pointed at recoverability:

| Stage | Question | Level reached | You already do this for code |
|---|---|---|---|
| Discover | onboarded for protection? | `DISCOVERED` | service discovery |
| Protect  | a policy attached? | `PROTECTED` | GitOps drift detection |
| Detect   | last backup clean? | `MONITORED` | observability / alerting |
| Recover  | is there a restorable point? | `RECOVERABLE` | rollback readiness / SLOs |
| Scan     | is the point you'd restore from clean? | `TRUSTED` | scanning an artifact before deploy |
| Validate | recovery *proven* by a real restore? | `VALIDATED` | **chaos drill / game day** |
| Improve  | did the level move since last run? | *(trend)* | regression gate |
| Continuous Service | safe to ship? | *(gate)* | required CI check |

Improve and Continuous Service aren't levels - they act *on* the state: Improve is the trend across runs (↑ climbed / = held / ↓ regressed) over a hash-chained audit trail; Continuous Service is the gate. There is **no FAIL state** - a read error (timeout/permission) doesn't invent a failure, it leaves you on the level below, named with the reason.

## Do it for real

**What's in the repo:** `config/workshop.yaml` - the one file you fill · `infra/` - the Terraform (workloads + platform) · `resops/` - the read-only engine + the `op` write lane · `config/tiers.yaml` + `config/frameworks/` - policy & the compliance packs.

### Before you start

The demo above needs **nothing**. For the live climb:

- **Azure** - a subscription + `az login`, and a backup service principal (you'll put its object id in `config/workshop.yaml`).
- **A data-protection tenant** (Commvault SaaS) - with an adopted hypervisor + managed storage pool (Setup step 1), and an access + refresh token.
- **Tools** - `python3` ≥ 3.9, `terraform`, `az`.

The path is linear: **demo → set up once → onboard → climb → gate → tear down.**

### Part 1 - Set up (once, ~15 min)

**1. Adopt the platform** - your one-time, provider-specific setup, done in the data-protection console (not in code). You're creating two things you set once and every workload reuses: a **hypervisor connection** to your Azure subscription (so the platform can see and protect your VMs) and a **managed storage pool** (where backups land). The read-only token is read-scoped, so this lives in the console, not Terraform. See your provider's console docs for the click-path; you'll copy the resulting ids into `workshop.yaml` next.

✓ **Done when** you can see the hypervisor + storage pool in the console and have their ids.

**2. Fill the `platform:` block of `config/workshop.yaml`** (copy `config/workshop.yaml.example`):

```yaml
platform:
  web_service_url: https://<tenant>.metallic.io/commandcenter/api
  subscription_id:        <azure-subscription-guid>
  commvault_sp_object_id: <backup-service-principal-object-id>
  hypervisor: { id: <client-id>, name: <name>, instance_id: <instance-id> }
  plan_id: <plan-id>
  storage_pool_name: <managed-pool-name>
```

> **Where to get `plan_id`:** two options — (a) create a plan in the console (Protect > Plans), then copy its id from the URL; or (b) run `infra/platform/` as Terraform code (`CV_TER_TOKEN` required) and copy from `terraform -chdir=infra/platform output plan_ids`. Either path lands in the same `plan_id` field — pick whichever suits your setup.

**3. Tokens + tools** - copy `.env.example` to `.env` and fill in `CV_ACCESS_TOKEN` + `CV_REFRESH_TOKEN` (Command Center > avatar > Access Tokens > Add); `az login`; `pip install -e .` (puts `op` + `resops` on PATH - use a **venv** to avoid touching your system Python). No install? Run `python3 -m resops …` / `python3 -m resops.operator.op …` instead.

> **`CV_TER_TOKEN`** (also in `.env.example`) is only needed if you run `infra/platform/` to create Commvault plans as Terraform code. If you created your plan manually in the console, leave it blank.

✓ **Done when** `python3 -m resops list` prints your protection groups (token + URL work).

### Part 2 - Onboard & climb (~20 min)

> ⚠️ **Real cloud, real cost.** The live climb creates an Azure VM (and a brief second one during
> the restore drill) - it costs money until `op teardown`, which the workshop always ends with.

```
 terraform apply  →  [discover]  →  op climb  →  op gate  →  op teardown
 provision           one-time       protect→backup→restore   PROMOTE/HOLD
```

**1. Declare** - the `workload:` block of `config/workshop.yaml` is the whole interface:

```yaml
workload:
  name: payments-api            # → VM name, its protection group, and the gate
  tier: tier1                   # must exist in config/tiers.yaml
  vm_size: Standard_F1als_v7    # optional
```

**2. Provision** - creates the VM + network and a restore-staging account, grants least-privilege IAM, and publishes the `workload` contract:

```bash
terraform -chdir=infra/workloads apply
```
✓ **Done when** `terraform -chdir=infra/workloads output workload` shows your VM.

**3. Discover** - tell the platform to scan your subscription so it *sees* the new VM. In production this runs on a schedule; in the workshop you trigger it once in the console (the read-only token can't, by design). Takes a minute or two.
✓ **Done when** `op preflight infra/workloads` shows `discovered … PASS`.

**4. Climb, gate, tear down:**

```bash
op preflight infra/workloads   # read-only gate: az · token · hypervisor · discovered · vCPU
op climb     infra/workloads   # protect → backup → restore → lands at VALIDATED
op gate      infra/workloads   # the verdict → PROMOTE (0) / HOLD (1) + compliance crosswalk
op teardown  infra/workloads   # protection group + snapshot, terraform destroy, region NetworkWatcher
#   op status infra/workloads  # the level, anytime (read-only)
```

Two things to expect: `op climb` **pauses at the restore step** (in a terminal) so you can look at the recovered VM - press **Enter** to tear that copy down and finish. And `op gate` **exits 1 until you reach `VALIDATED`** - that's a correct HOLD, not an error. Always `op teardown` when done; the VM costs money until you do.

As it climbs, `op status` fills the dots in - and the gate gives the verdict:

```
 ●●●●●●  VALIDATED  ·  recovery proven - job <id>
 PROMOTE  recoverability proven · exit 0
```

✓ **Done when** `op gate` prints `PROMOTE · exit 0` - a workload that's *provably* recoverable, with the evidence to show an auditor. (No hardcodes: `op` reads two inputs - the `workload` terraform output and `config/workshop.yaml`; runtime specifics come from the live API.)

🎉 You just proved an Azure workload is recoverable - as code, gated, with audit evidence. **That's ResOps.**

### Part 3 - Break trust on purpose (~10 min, optional)

A clean climb proves your workload is **recoverable**. It proves nothing about whether the thing you'd recover *from* is **trustworthy** - and in a real incident that's the question that matters. A compromised service doesn't just go down; recent backups may carry the compromise with them.

So break it, on purpose, and watch the same tool reach the opposite verdict:

```bash
op incident  infra/workloads   # plant a detectable compromise in the workload
op backup    infra/workloads   # the incident is now INSIDE a recovery point
op restore   infra/workloads   # restore it in isolation, then READ what came back
op gate      infra/workloads   # HOLD · exit 1
```

```
 ●●●●✗·  RECOVERABLE  blocked at Scan
 ↳ recovery point failed restore-verify - 14 encrypted (.locked) files present
 HOLD  exit 1
```

Same workload, same commands, opposite verdict - because the recovery point is no longer trustworthy. Note *what caught it*: not a scan verdict, but `/opt/app/verify.sh` - thirty lines of shell your workload ships, run **inside the restored copy**. Code present, baseline intact, records readable, no encryption markers. The one line it prints - `OK:` or `FAIL:` - is the attestation. The contract is in [VERIFY.md](VERIFY.md): it's the one file you have to write yourself, and the one nobody can write for you.

### Why a script and not a backup-product scan

We tried two shortcuts first and both were blind:

| Attempt | Result |
|---|---|
| Threat scan on the backup | **works** - proven 2026-08-12: two planted EICAR files found inside an Azure VM image backup, with a clean scan either side of the dirty one. It missed fourteen encrypted files that `verify.sh` caught. A second attester, not a substitute |
| Dedupe ratio as an integrity signal | the same idle VM ranges **57.9% - 99.7%**; 42 points of natural variance is noise, not signal |

There is no way to know a backup is good without opening it - **you have to look inside.** The vendor's scan does look, for what *it* recognises. Only your own check knows whether *your* service still works. `restore-verify` is the attester you own end to end, and its verdict is one anybody in the room can read.

#### What a threat scan on an Azure VM actually needs

Less than we spent six weeks believing. A scan found two planted EICAR files on a VM group `op protect` had created and nobody had touched:

```
 collectFileDetailsforGranularRecovery   False
 enableFileIndexing                      never set
 IntelliSnap                             off
 Indexing V2                             on        ← the one documented
                                                     prerequisite, already on
```

**It works on the defaults.** This section previously listed four requirements including `enableFileIndexing`. That was wrong: we never set that field on the group that worked.

The VM does need to be listed in a threat scan group with a scan plan attached, and association can be automatic. Beyond that, two triggers work and one does not:

```
 POST TaskOperation                  plan-level. fans out one job per subclient
   {opType RUN, subtaskEntity[…],    in the group. derive taskId from the scan
    taskIds[…]}                      plan and subtaskId from Schedules.
 POST ThreatIndicator/OnDemandScan   per-resource. ONE VM, ONE job id returned.
   {clients[{tdPlan, client{…}}],    Does NOT require the VM to appear in the
    type 0, levelType 1}             Resources tab yet. UNDOCUMENTED - absent
                                     from the API reference and the vendor SDK.
 POST EDiscoveryClients/             creates a Threat Hunting job that never
   OnDemandAnalytics                 binds to a VSA subclient and reports "no
                                     new backup data". This is the one the
                                     vendor SDK uses. Dead end for VMs.
```

Read the verdict from `GET Client/Anomaly`, keyed on the VM's `client.clientId`, at `vsaSecurityScanAnomalyInfo.malwareItemsCount`. **Never read job success as clean** - a re-scan of a poisoned point with no new backup data completes with no error and no verdict.

And if a scan fails, suspect the group before the product. A group whose VM has been deleted fails every time with `[14:313]`, while identically configured groups in the same tenant succeed.

With all four in place our jobs bind, reach `Process: FileScan`, and then stall on `[14:313]`, a remote-file-cache fault between two vendor-operated media agents. That is where it sits: correct on our side, unresolved on theirs, and still no verdict ever produced.

An attestation also has a **shelf life**: "verified once, a year ago" is not verified. `config/tiers.yaml` sets `attestation_max_age_days` per tier (tier1 30d, tier2 90d), and a stale attestation is a hard HOLD with no override.

`op incident` plants the **EICAR test pattern** (the industry-standard harmless string) plus a burst of high-entropy `.locked` files, which is what mass encryption looks like on disk. Nothing is really encrypted and no malware is involved; the known-good `BASELINE` marker is left in place so *"what did we still trust?"* has an answer.

> ⚠️ `op incident` deliberately makes a workload dirty. It targets only the VM in your Terraform contract, and `op teardown` plus a fresh climb restores a clean one. Never point it at anything you care about.

Reverse the order and you get the workshop's whole point in two lines: **the backup completed successfully, and it is still not safe to restore from.**

## Why it's real - compliance, by design

The same recovery evidence maps onto **DORA / NIST 800-53 / APRA CPS 230** automatically - that crosswalk is what makes this ResOps, not a backup script. Each capability (asset identification, backup coverage, monitoring, recovery readiness, recovery proof) maps to its control, so a GAP isn't just "a backup failed," it's "DORA Art. 12 unmet." Enable the packs under `gate:`:

```yaml
gate:
  frameworks: [dora, nist-800-53, apra-cps230]
```

Every run writes `evidence/` - `report.md` (a **Controls** column), `bundle.json`, JUnit, and a hash-chained history. **`op gate` exits 0 (PROMOTE) only at `VALIDATED` with fresh proof** (`gate.recovery_proof_max_age_days`, default 7), else exit 1 (HOLD). Wire it as a required CI check so recoverability drift fails the pipeline like a failing test - a ready-to-use workflow ships in [`.github/workflows/resops-gate.yml`](.github/workflows/resops-gate.yml). *(The mapping is indicative - it supports a resilience programme, not a formal attestation.)*

## How it works under the hood

- **Protect by id.** `op protect` adds the VM to its protection group by its Azure `vmId` (free from `terraform output vm_guid`) - a thin, direct write through the API that the read-only ladder can verify, while Terraform owns the Azure resources.
- **Streaming backups.** A clean path with fewer moving parts - every backup is immediately restorable and teardown stays simple.
- **Least-privilege IAM.** Terraform grants the backup service principal exactly the roles backup and restore need - nothing more - plus a per-workload staging account for the restore.
- **Derived, not hand-crafted.** The restore request is built from live reads + the Terraform contract - nothing to capture or maintain by hand.
- **Clean teardown.** `op teardown` removes the managed snapshot a backup leaves, then `terraform destroy` clears the rest - the resource group goes away cleanly, nothing lingers or costs.
- **Fresh name each run.** `resops` resolves a workload by name, so give each new one its own codename rather than reusing a retired one.
- **Tokens & capacity.** `op` refreshes the API token automatically each run (`resops list` refreshes on demand); pick a region/size with spare vCPU - a restore briefly runs a second VM beside the source.

## In production

`infra/platform/` is the platform team's paved road (an adopted hypervisor + storage + a policy per tier from `config/tiers.yaml`); `infra/workloads/` is a PR per app team. You **don't** run `op climb` - recoverability comes from the tier's backup schedule (the RPO you declared), and the gate confirms it on every PR + a daily run. Same muscle as a required test or a security scan: a workload doesn't promote unless it's provably recoverable.
</content>

## Before you run this in your own tenant

Everything above works offline against committed fixtures. The moment you point it at a real subscription and a real data-protection tenant, these are the things that cost us hours. None are obvious and most fail quietly.

### The one that fails silently

**`platform.commcell_id` defaults to `2`.** That is the common value for a single-CommCell Metallic instance, and it is not universal. It goes into the restore request's `commCellId`. A wrong value is **accepted**, browses the wrong CommCell, and comes back looking like an empty backup rather than like an error. Check yours before the first live restore - any job's `commCellId` in the API will tell you.

### Azure

```
 SP Object ID ≠ App Registration Object ID     different GUIDs, and the
                                               error if you use the wrong
                                               one is an unhelpful 403
   az ad sp show --id <appId> --query id -o tsv

 GXMD snapshots block resource-group deletion  a backup leaves one, and it
                                               does NOT appear in az disk list
 Recovery Services vaults block it too         `op teardown` sweeps both
 changing custom_data forces VM replacement    same trap as os_disk.name.
                                               fine on a fresh climb,
                                               never mid-drill
 a restore briefly runs a SECOND VM            size your regional vCPU quota
                                               for two, not one
```

### The data-protection tenant

```
 backup job "Waiting" for 5-15 min is NORMAL   it is queueing for a media
                                               agent. do not kill it.
 tokens die on a hard wall                     renewal fails with HTTP 500
                                               "Renew request placed after
                                               the permissible time limit",
                                               which reads like a server
                                               fault and is auth. run
                                               `resops list` first, always.
 vmgroup_id is ephemeral                       resolved live by name
                                               (resops-<name>-vg). never
                                               hard-code it.
 use a FRESH workload codename every run       see below
```

**On codenames.** In our tenant `DELETE /v4/VMGroup/{id}` returns HTTP 202 *"pending administrator authorization"*. The group vanishes from listings, which reads exactly like success, and if nobody approves it, it comes back. So every run leaves an undeleteable group behind. Reusing a retired name makes `op protect` adopt the stale group and attach it to a dead VM GUID - and that failure surfaces later, at backup, reading like nothing at all. Give every run its own codename. Check whether your tenant behaves the same way before assuming it does not.

### What is proven, and what is not

Be careful which of these you repeat as fact. The project has already paid once for stating an unproven thing confidently.

```
 PROVEN LIVE      the full climb to VALIDATED, the restore drill, and all
                  four attestation verdicts - unattested, dirty, stale, clean
 PROVEN LIVE      the compromised-backup path: every vendor signal green,
                  the recovery point still poison
 PROVEN LIVE      the write lane is REPEATABLE. Two consecutive passes of the
                  14-step loop, 2026-08-12, every exit code as expected - three
                  of them non-zero by design - with no step re-run and no
                  improvising by the person running it.
 PROVEN LOCALLY   the observability stack, 12/12 checks in Docker.
                  NEVER applied to Azure.
 PROVEN           threat scan DETECTS malware in an Azure VM image backup
                  here, on default settings. 2026-08-12: two planted EICAR
                  files found, error 91:711, malwareItemsCount 2, with a
                  clean scan either side of the dirty one.
 NOT PROVEN       that its ENCRYPTION detection fires. Fourteen high-entropy
                  .locked files went unreported in the same scan that found
                  the EICAR. verify.sh caught all fourteen and missed the
                  EICAR. Neither attester is sufficient alone.
 NOT SCOPED       Synthetic and Forensic recovery. Both are documented, both
                  are offered in the restore wizard for this VM, neither has
                  been executed here.
 NOT WRITTEN      verify.sh worked examples for managed databases and object
                  storage. The contract transfers; the examples do not exist.
 NO MODEL         the cost of restore-verify at production data volume.
                  Sampling plus a per-tier freshness bar is a policy, not a
                  number.
```

## Maintainer

Maintained by [@ntcsteve](https://github.com/ntcsteve). Open an issue for questions, corrections, or if you get an adapter working against a different data-protection platform.

**Be warned about what porting costs today.** `gate()`, the evidence chain, the crosswalk, the metrics and the renderer are genuinely vendor-neutral. `client.py` + `reads.py` (~450 lines) do the I/O. But `classify()` - the ladder - reads Commvault's field names directly, so an adapter must currently produce Commvault-shaped dicts rather than simply supplying facts. A neutral seam between the two is designed and not built. That is the first thing to fix if you are porting, and an issue saying so would be welcome.
