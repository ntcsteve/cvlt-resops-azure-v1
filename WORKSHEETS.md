# Worksheets

> Six sheets. Print them, or copy each into a shared doc — one page per sheet.
> Sheets 2, 5 and 6 are the ones you take home and use.

> Participants: [WORKSHOP.md](WORKSHOP.md) is the guide these belong to.
> Facilitators: [FACILITATOR.md](FACILITATOR.md), and collect sheet 1 at M1.2 —
> you hand it back at the close and the delta is the day's only measurement.

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

   ______________________________________________________________
```

**3. How long would producing that proof take?**

```
   ☐ minutes    ☐ hours    ☐ days    ☐ weeks    ☐ I could not
```

> You get this back at 16:00. If your answer has not changed, tell the facilitator.

---

# Worksheet 2 · Trust map

**M1.3 · 35 minutes · KEEP THIS — it is scored in M6**

**Scenario.** `orders-api`, tier-1 payments, 41,892 customer records. A deployment landed Tuesday. A storage credential with broad access was over-permissioned and used from an unrecognised address. This morning there is a `README_RECOVER.txt` in the data directory. The service is still responding. Dashboards are green.

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

**5. Your backups. Trusted, untrusted, or unknown — and why?**

```
   ☐ trusted   ☐ untrusted   ☐ unknown

   ______________________________________________________________
```

---

# Worksheet 3 · Trusted Recovery Pattern — the scenario

**M3.2 · 25 minutes**

One or two concrete actions per step. Not phrasing. What you would actually do on the morning you found that note.

```
 1  MAP TRUST BOUNDARIES
    (you did this on worksheet 2 — carry the conclusion here)
    ____________________________________________________________

 2  FIND TRUSTED PROTECTED STATE
    which copies survived the same blast radius?
    ____________________________________________________________
    ↳ could the misused credential reach them?   ☐ yes ☐ no ☐ unknown

 3  LABEL RECOVERY POINTS
    which are clean, which are suspect, which has nobody looked at?
    ____________________________________________________________

 4  CHOOSE OR CONSTRUCT THE CLEANEST VIABLE POINT
    ____________________________________________________________

 5  CAPTURE EVIDENCE AND LEARNING
    ____________________________________________________________
```

---

# Worksheet 4 · Checks that could pass having examined nothing

**M4.2 · 10 minutes**

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

# Worksheet 5 · The decision

**M6.1, 6.4 and 6.5**

### Part A · Predict · M6.1 · before anything runs

From worksheet 2. Which survive the incident?

```
 code       ☐ survives   ☐ does not        actual: ____   ☐ right ☐ wrong
 state      ☐ survives   ☐ does not        actual: ____   ☐ right ☐ wrong
 config     ☐ survives   ☐ does not        actual: ____   ☐ right ☐ wrong
 identity   ☐ survives   ☐ does not        actual: ____   ☐ right ☐ wrong
 BASELINE   ☐ survives   ☐ does not        actual: ____   ☐ right ☐ wrong

 SCORE  ___ / 5
```

### Part B · Choose a recovery point · M6.4

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

   ______________________________________________________________
```

**The gate promoted D. Do you agree with the gate? Why or why not?**

```
   ______________________________________________________________
```

### Part C · Evidence outline · M6.5

What would you show each of these, the morning after?

```
 YOUR LEADERSHIP   ___________________________________________

 AN AUDITOR        ___________________________________________

 YOUR OWN TEAM     ___________________________________________

 Which of the three is hardest to produce today, and why?
   ______________________________________________________________
```

---

# Worksheet 6 · Your workload, and one next action

**Close · 15 minutes · THIS IS THE ONE THAT MATTERS**

**Pick one real workload you own, influence, or support.**

Name: ______________________  Tier / criticality: ______________________

### The pattern, for that workload

```
 1  what becomes UNTRUSTED in a similar event?
    ____________________________________________________________

 2  what trusted protected state exists TODAY, if any?
    ____________________________________________________________

 3  which recovery points would most need validation?
    ____________________________________________________________

 4  where would a curated or constructed point reduce loss?
    ____________________________________________________________

 5  what part of your current recovery story is hardest to PROVE?
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
 L1  SEE       resops gate — read-only, cannot mutate anything     day 1
 L2  DECLARE   verify.sh for ONE tier-1 workload. 20 lines.        week 1
 L3  PROVE     one scheduled drill. one attestation.               week 2
 L4  GATE      required check on that ONE workload. ratchet.       month 1
 L5  PUBLISH   resops metrics on a wall.                           quarter 1
```
