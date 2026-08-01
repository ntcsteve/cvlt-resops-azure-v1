# Trusted Recovery for Cloud-Native Workloads

> **Participant guide.** Work through it at your own pace. The facilitator floats.
> Every command is copy-paste. You should never need to type a path from memory.

**Level** 300-400 · **Duration** 7h10m door to door · **Audience** platform engineers, SREs, cloud architects

---

## The one idea

```
 You gate on tests.
 You gate on security scans.
 You do not gate on recoverability.
```

Everything today is supporting material for that sentence. If you leave with nothing else, leave with the question it implies: *how much of your estate could you prove is recoverable, right now, to someone who did not believe you?*

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

### What runs where

```
 OFFLINE      no cloud, no token, one second, cannot fail
 LIVE         a real Azure VM, already provisioned for you
 WATCH        the facilitator drives; you do not need to follow along
```

Your workload was provisioned and climbed to VALIDATED before you arrived. You are not going to spend the morning on terraform.

### Before you start

```bash
cd ~/resops-cvlt-azure
source .venv/bin/activate
```

```
 ✓ YOU SHOULD SEE   the prompt change to (.venv)
 ✗ IF NOT           ask. do not continue — everything below depends on it.
```

---

# M1 · Recovery under broken trust

**60 minutes · OFFLINE**

**Objective:** establish that a service can be fully available and still be operationally untrusted, and produce the trust map you will test in M6.

---

## 1.1 · See the gap  ·  10 min  ·  OFFLINE

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

   — and the other four blocked at Validate, Detect, Recover and Discover,
   then a final line:

   AGGREGATE  HOLD — checkout-api, identity-svc, reporting-db,
                     edge-cache, legacy-batch · exit 1

 ✗ IF NOT     `pip install -e .` then try again.
```

Read the six workloads top to bottom. The **bar** is the six stages, the **state** is where you stopped, and **blocked at** names the stage that did not clear.

Six dots, six stages. You stop at the first stage that does not clear, and that rung **is** your state. The stage you are stuck on is the next thing to fix.

**Stop on `checkout-api`.** Protected. Backups completing. SLA met. Recovery *proven* by a real restore. Every light green, and it still must not ship, because the point it would restore from carries a threat.

```
 ? WHY THIS MATTERS

   Available is not the same as trusted. Every other row on that
   screen is a problem you already know how to describe. That one
   is not, and it is the reason the Scan stage exists.

   Note checkout-api and identity-svc sit on the SAME rung for
   opposite reasons — one was tested and is contaminated, one was
   never tested. The rung alone hides that. The blocked stage names it.
```

---

## 1.2 · Your number  ·  5 min  ·  WORKSHEET 1

Take the card. Write your answer. Fold it. Give it to the facilitator. You get it back at 16:45.

```
 1. What percentage of your production estate could you PROVE
    is recoverable today?

 2. How would you prove it, to someone who did not believe you?

 3. How long would producing that proof take?
```

```
 ? WHY THIS MATTERS

   This is the only measurement the day makes. Everything else is
   opinion. If your answer at 16:45 is the same as your answer now,
   we wasted your time and I would like to know.
```

---

## 1.3 · Trust map  ·  35 min  ·  WORKSHEET 2

### The scenario

`orders-api` is a tier-1 payments service. 41,892 customer records.

A deployment landed on Tuesday. A storage credential with broad access was over-permissioned and has been used from an address nobody recognises. This morning there is a file called `README_RECOVER.txt` in the data directory.

The service is still responding. Requests are being served. Dashboards are green.

### The four categories

Every workload, at every size, is made of four things. Yours has forty services and six managed data stores; it is still these four categories, just more of each.

```
 CODE       what executes            did this come from the pipeline?
 STATE      what it has written      it changed after the deploy. expected?
 CONFIG     what shapes behaviour    who can write this?
 IDENTITY   what it can reach with   this is the blast radius
```

In today's lab those are four concrete things you can point at:

```
 CODE      /opt/app/serve.sh · /opt/app/VERSION
 STATE     /var/lib/app/data/  (customers.csv · orders.ndjson · BASELINE)
 CONFIG    /etc/app/config.yml       world-readable, on purpose
 IDENTITY  /etc/app/creds.env        the storage key
```

### The exercise

For each of the four, mark it and justify it in one line.

```
 TRUSTED     I would run production on this as-is, and here is why
 UNTRUSTED   I have positive reason to doubt it
 UNKNOWN     I have no evidence either way
```

Then two harder questions:

```
 4. What single piece of missing information would move the most
    boxes out of UNKNOWN?

 5. Your backups. Trusted, untrusted, or unknown — and why?
```

```
 ? WHY THIS MATTERS

   UNKNOWN is the honest answer far more often than people write,
   and a box you cannot justify is worth more to you today than a
   confident one. Question 5 is the one the rest of the day answers.

   Keep this sheet. In M6 you will find out which boxes you got
   right, and it will be scored.
```

---

## M1 outputs

```
 ✓ your sealed number                    worksheet 1, facilitator holds it
 ✓ a trust map for orders-api            worksheet 2, KEEP THIS
 ✓ a question you cannot yet answer      "how much of MY estate?"
```

---

# M2 · Recoverability as code

**50 minutes · OFFLINE** — *to be drafted*

```
 2.1  Predict the blocked stage                       10m
 2.2  The ratchet — adopt without going red    E5     15m
 2.3  Twenty lines of CI                              10m
 2.4  Making it the default                           15m
      ↳ the paved road · tiers · who owns what
      ↳ "does this page me?"  no. it fails a PR.
```

# M3 · The Trusted Recovery Pattern

**50 minutes · WORKSHEET 3** — *to be drafted*

```
 3.1  The five steps                                  10m
 3.2  Write it for the scenario                E3     25m
 3.3  The blast-radius question  →  AIR GAP           15m
```

# M4 · Verify your verifier

**30 minutes · WORKSHEET 4** — *to be drafted*

```
 4.1  A job record. Ship or hold?               E6     20m
 4.2  Three checks in YOUR pipeline                    10m
```

# M5 · Lab — declare and prove

**75 minutes · LIVE** — *to be drafted*

```
 5.1  op gate — your workload, already climbed  E7     20m
 5.2  Write a verify check for YOUR shape       E8     35m
      ↳ VM (bash) · managed DB (SQL) · bucket · k8s
      ↳ then compare. the contract does not change.
 5.3  Teardown                                         10m
```

# M6 · Game day

**75 minutes · LIVE + OFFLINE · WORKSHEET 5** — *to be drafted*

```
 6.1  Predict, from your M1 trust map           E9a     5m   SCORED
 6.2  op incident → op backup                          10m
 6.3  op restore → op gate                             20m
 6.4  Four recovery points. Choose.             E10    25m
      python3 -m resops gate config/incident.yaml
 6.5  Evidence, and what you would show         →  REPORTING
```

# Close

**15 minutes · WORKSHEET 6** — *to be drafted*

```
 Unseal worksheet 1. Write the real number.
 One next action, named, with a date.
 The day-7 question: did you run it against anything real?
```
