# Worksheets

> Six sheets. Print them, or copy each into a shared doc – one page per sheet.
> Sheets 2, 4 and 6 are the ones you take home and use.

> Participants: [WORKSHOP.md](WORKSHOP.md) is the guide these belong to.
> Facilitators: collect sheet 1 at M1.2 – you hand it back at the close and the
> delta is the day's only measurement. The full runbook is shared directly.

```
 W1  M1.2   your number          sealed, returned at the close
 W2  M1.3   trust map            KEEP IT – scored in M5.1
 W3  M3.2   three checks         take home
 W4  M4.2   your verify contract take home
 W5  M5     predict · choose · evidence
 W6  Close  YOUR workload + one next action
```

---

# Worksheet 1 · Your number

**M1.2 · 5 minutes · fold it and hand it in**

Name / table: ______________________

**1. What percentage of your production estate could you PROVE is recoverable today?**

```
        %  ______
```

**2. How would you prove it, to someone who did not believe you?**

```
   ______________________________________________________________
```

**3. How long would producing that proof take?**

```
   ☐ minutes    ☐ hours    ☐ days    ☐ weeks    ☐ I could not
```

> You get this back at the close. If your answer has not changed, tell the facilitator.

---

# Worksheet 2 · Trust map

**M1.3 · 35 minutes · KEEP THIS – it is scored in M5.1**

**Scenario.** `orders-api`, tier-1 payments, 41,892 customer records. A deployment landed Tuesday. A storage credential with broad access was over-permissioned and used from an unrecognized address. This morning there is a `README_RECOVER.txt` in the data directory. The service is still responding. Dashboards are green.

Mark each and justify in one line. **UNKNOWN is a real answer and often the honest one.**

```
 ┌──────────┬───────────────────────────┬─────────┬───────────┬─────────┐
 │ CATEGORY │ IN THE LAB                │ TRUSTED │ UNTRUSTED │ UNKNOWN │
 ├──────────┼───────────────────────────┼─────────┼───────────┼─────────┤
 │ CODE     │ /opt/app/serve.sh         │    ☐    │     ☐     │    ☐    │
 │          │ /opt/app/VERSION          │         │           │         │
 │ why:     │                                                           │
 ├──────────┼───────────────────────────┼─────────┼───────────┼─────────┤
 │ STATE    │ /var/lib/app/data/        │    ☐    │     ☐     │    ☐    │
 │          │ customers.csv · BASELINE  │         │           │         │
 │ why:     │                                                           │
 ├──────────┼───────────────────────────┼─────────┼───────────┼─────────┤
 │ CONFIG   │ /etc/app/config.yml       │    ☐    │     ☐     │    ☐    │
 │          │ world-readable            │         │           │         │
 │ why:     │                                                           │
 ├──────────┼───────────────────────────┼─────────┼───────────┼─────────┤
 │ IDENTITY │ /etc/app/creds.env        │    ☐    │     ☐     │    ☐    │
 │          │ the storage key           │         │           │         │
 │ why:     │                                                           │
 └──────────┴───────────────────────────┴─────────┴───────────┴─────────┘
```

**4. What single missing fact would move the most boxes out of UNKNOWN?**

```
   ______________________________________________________________
```

**5. Your backups. Trusted, untrusted, or unknown – and why?**

```
   ☐ trusted   ☐ untrusted   ☐ unknown

   ______________________________________________________________
```

> M1.4 answers question 5. Note what changes your mind, if anything does.

---

# Worksheet 3 · Checks that could pass having examined nothing

**M3.2 · 10 minutes**

```
 THE RULE
   Absence of evidence is not evidence of absence.
   A check that ran nothing must never report a pass.
```

**Name three checks in YOUR pipeline that could pass having examined nothing.**

```
 1  the check      ______________________________________________
    how it lies    ______________________________________________
    how I'd know   ______________________________________________

 2  the check      ______________________________________________
    how it lies    ______________________________________________
    how I'd know   ______________________________________________

 3  the check      ______________________________________________
    how it lies    ______________________________________________
    how I'd know   ______________________________________________
```

Starters: a test filter that matched 0 tests · a scanner with no ruleset for that language · a coverage gate with no coverage file · terraform plan against an empty workspace · a smoke test hitting a CDN cache · **an alert on a metric that stopped being emitted**.

---

# Worksheet 4 · Your verify contract

**M4.2 · 35 minutes · TAKE THIS HOME – it is L2 of the adoption ladder**

**My workload shape:** ☐ VM ☐ managed DB ☐ object storage ☐ kubernetes ☐ other ______

**The four rules. Pseudocode counts.**

```
 1  the verdict LINE is authoritative      OK: / FAIL:
 2  ONE line per message                   the parser stops at the first
 3  print the verdict LAST                 then exit
 4  no verdict means UNATTESTED            never clean
```

**What "good" looks like for my workload. Aim for checks that need the data OPENED.**

```
 1  ________________________________________________________
    FAIL: ___________________________________________________

 2  ________________________________________________________
    FAIL: ___________________________________________________

 3  ________________________________________________________
    FAIL: ___________________________________________________

 4  ________________________________________________________
    FAIL: ___________________________________________________

 OK: _______________________________________________________
```

```
 GOOD                                WEAK
 the file PARSES                     the file exists
 row counts in an expected range     the disk is the expected size
 a known-good marker is present      the timestamp looks recent
 schema is what you expect           the service starts
```

**Compared with the table next to me. Their shape: ____________ What was the same?**

```
   ______________________________________________________________
```

---

# Worksheet 5 · The decision

**M5.1, 5.4 and 5.5**

### Part A · Predict · M5.1 · before anything runs

From worksheet 2. Which survive the incident?

```
 code       ☐ survives   ☐ does not        actual: ____   ☐ right ☐ wrong
 state      ☐ survives   ☐ does not        actual: ____   ☐ right ☐ wrong
 config     ☐ survives   ☐ does not        actual: ____   ☐ right ☐ wrong
 identity   ☐ survives   ☐ does not        actual: ____   ☐ right ☐ wrong
 BASELINE   ☐ survives   ☐ does not        actual: ____   ☐ right ☐ wrong

 SCORE  ___ / 5
```

### Part B · Choose a recovery point · M5.4

```
 D  7 hours ago    attested clean       RPO 7h        gate: PROMOTE
 C  32 hours ago   UNATTESTED           RPO 32h       gate: HOLD
 B  6 days ago     attested clean       RPO 144h      gate: HOLD
 A  400 days ago   attested 400d ago    RPO 9600h     gate: HOLD

 The fact you do NOT have: the first anomalous log entry is
 "sometime last week". Retention is 7 days and the earliest
 surviving entry is already abnormal.
```

**I choose:** ☐ D  ☐ C  ☐ B  ☐ A  ☐ none of them

**In one sentence, naming what I give up:**

```
   ______________________________________________________________
```

**The gate promoted D. Do you agree with the gate? Why or why not?**

```
   ______________________________________________________________
```

### Part C · Evidence outline · M5.5

```
 YOUR LEADERSHIP   ___________________________________________

 AN AUDITOR        ___________________________________________

 YOUR OWN TEAM     ___________________________________________

 Which is hardest to produce today, and why?
   ______________________________________________________________
```

---

# Worksheet 6 · Your workload, and one next action

**Close · 20 minutes · THIS IS THE ONE THAT MATTERS**

You have walked all five steps today. Now write them for something real.

**Workload:** ______________________  **Tier / criticality:** ______________

### The pattern, for your workload

```
 1  WHAT DO I STILL TRUST?
    what becomes untrusted in a similar event?
    ____________________________________________________________

 2  WHICH COPIES SURVIVED THE BLAST RADIUS?
    what trusted protected state exists TODAY, if any?
    ____________________________________________________________

 3  WHICH RECOVERY POINTS ARE CLEAN?
    which would most need validation, and who would do it?
    ____________________________________________________________

 4  WHICH ONE DO I PICK?
    where would a curated or constructed point reduce loss?
    ____________________________________________________________

 5  HOW DO I JUSTIFY IT AFTERWARDS?
    what part of your recovery story is hardest to PROVE?
    ____________________________________________________________
```

### Your number, revisited

```
 This morning I said        ______ %
 Now I would say            ______ %
 What changed my answer:  ______________________________________
```

### One next action

Pick exactly one. Name it. Date it.

```
 ☐ a runbook or incident-process change
 ☐ a platform or control-default change
 ☐ an evidence or reporting improvement

 WHAT   ______________________________________________________
 WHO    ______________________________________________________
 BY     ______________________________________________________
```

```
 In seven days you get one question:
 did you run it against anything real?
```

### Where to start on Monday

```
 L1  SEE       resops gate – read-only, cannot mutate anything     day 1
 L2  DECLARE   verify.sh for ONE tier-1 workload (worksheet 4)     week 1
 L3  PROVE     one scheduled drill. one attestation.               week 2
 L4  GATE      required check on that ONE workload. ratchet.       month 1
 L5  PUBLISH   % provably recoverable, on a wall.                  quarter 1
```
