"""WORKSHOP.md is executable documentation, and this is what keeps it true.

WHY THIS EXISTS. The first draft of M1 pasted the README's estate block into a
"you should see" box. The README block is an illustration – the real tool prints
a ▸ header line, a bar line and a reason line per workload, and no summary
column. In a room, twenty people would have compared their screen to the guide,
found it different, and stopped trusting the guide on page one.

A workshop guide that lives in the repo only beats a hosted one if it is
VERIFIED here. Otherwise it is a website with worse hosting.

Two directions of drift, both caught:

  the TOOL changes   → `must_contain` stops appearing in the output
  the GUIDE changes  → `command` is no longer found verbatim in WORKSHOP.md

Only OFFLINE steps run here. Live steps need a tenant and are the facilitator's
rehearsal, not CI's job. Every offline step in the guide belongs in this list.
"""
import re
import shlex
import subprocess
import sys

from resops.__main__ import ROOT

GUIDE = ROOT / "WORKSHOP.md"

# The two-hour form. A SECOND guide is a SECOND drift surface, so it is bound by
# the same tests rather than trusted. Its offline steps are a subset of the
# six-hour day's, which is why OFFLINE_STEPS covers both: each command must appear
# verbatim in at least one guide, and must still produce what that guide promises.
GUIDE_2H = ROOT / "WORKSHOP-2H.md"
GUIDES = (GUIDE, GUIDE_2H)
ANSI = re.compile(r"\x1b\[[0-9;]*m")

OFFLINE_STEPS = [
    # ---- ADDED 2026-08-20 ------------------------------------------------
    # The guide's Overview now PRINTS a claim about where its expected outputs
    # come from: "re-run by the suite that gates this build". Four of the 2h
    # guide's seven offline commands were covered when that claim was drafted,
    # so the other three plus the report were added rather than the claim
    # softened: the guide's offline commands should all be re-run and
    # compared, not just the four that happened to be covered first.
    #
    # `cat` and `grep` steps are here for the same reason as the resops ones:
    # the guide quotes what they print, so an edit to tiers.yaml or to the
    # cloud-init verify.sh silently falsifies a box unless something re-reads
    # it. That is exactly how the verify.sh length drifted across five docs.
    {
        "module": "2h ch2 – the policy file",
        "command": "cat config/tiers.yaml",
        "exit_code": 0,
        "must_contain": [
            "rpo_hours",
            "rto_minutes",
            "attestation_max_age_days",
        ],
    },
    {
        "module": "2h ch2 – read the verifier",
        "command": ("grep -A 80 'path: /opt/app/verify.sh' "
                    "infra/modules/azure-vm/cloud-init.yaml"),
        "exit_code": 0,
        # The box promises "about seventy lines carrying five checks", that the
        # last one WRITES and reads back, and that the script ends at exit 0.
        "must_contain": [
            "write/read verified",
            "exit 0",
        ],
    },
    {
        "module": "2h ch6 – the crosswalk",
        "setup": "python3 -m resops gate config/estate.yaml",
        "command": "cat evidence/estate/payments-api/report.md",
        "exit_code": 0,
        "must_contain": [
            "CAP-RESTORE-TESTED",
            "Indicative",
            "not a compliance attestation",
        ],
    },
    {
        "module": "2h ch6 – the gate as CI",
        "command": "cat .github/workflows/resops-gate.yml",
        "exit_code": 0,
        "must_contain": [
            "pull_request:",
            "schedule:",
        ],
    },
    {
        "module": "M1.1 – see the gap",
        "command": "python3 -m resops gate config/estate.yaml",
        "exit_code": 1,
        "must_contain": [
            "▸ payments-api",
            "●●●●●●  VALIDATED",
            "●●●●✗·  RECOVERABLE",
            "blocked at Scan",
            "recovery point failed restore-verify",
            "AGGREGATE  HOLD",
        ],
    },
    {
        "module": "M2.4 – publish the judgment",
        "command": "python3 -m resops metrics config/estate.yaml",
        "exit_code": 0,
        "must_contain": ["resops_rung", "resops_promotable", "resops_tolerated"],
    },
    {
        "module": "M5.4 – four recovery points",
        "command": "python3 -m resops gate config/incident.yaml",
        "exit_code": 1,
        "must_contain": [
            "▸ D-7-hours-ago",
            "PROMOTE",
            "recovery point is UNATTESTED",
            "rpo 144.0h > target 8h",
            "attestation stale (400.0d > 30d)",
        ],
    },
    {
        # Runs after M5.4 in the guide, which is what writes the chain it audits.
        "module": "M5.5 – the audit trail",
        "command": "python3 -m resops verify config/incident.yaml",
        "exit_code": 0,
        "must_contain": ["audit trail intact"],
    },
]

# Files the PUBLISHED guides point at. A dead link in a room is a facilitator
# improvising, so they are checked like anything else.
LINKED_FILES = ("WORKSHEETS.md", "VERIFY.md", "RESOPS.md",
                "README.md", ".github/workflows/resops-gate.yml",
                "config/estate.yaml", "config/incident.yaml")

# Gitignored: it carries delivery coaching, the "what you must not claim" list,
# and tenant-specific investigation detail, so it is shared directly rather than
# published. Present for a maintainer, absent in a fresh clone – checked only
# when it is there, so the suite passes in both.
PRIVATE_DOCS = ("FACILITATOR.md",)


def _run(command: str):
    # shlex, not .split(): a naive whitespace split shatters a quoted argument,
    # so `grep -A 80 'path: /opt/app/verify.sh' file` became four broken words
    # and grep exited 2. The command must be tokenized the way a shell does.
    argv = shlex.split(command.replace("python3", sys.executable, 1))
    proc = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True)
    return proc.returncode, ANSI.sub("", proc.stdout + proc.stderr)


def test_every_offline_command_is_actually_in_the_guide():
    """Catches the guide being edited away from what CI verifies.

    Checks BOTH guides. The rule at the top of this file always said each
    command must appear verbatim in at least one of them, but this test only
    ever read WORKSHOP.md, so a command that lives solely in the 2h guide
    could not be verified here at all. Found on 2026-08-20 when the four
    remaining 2h offline commands were added."""
    texts = [g.read_text() for g in GUIDES]
    for step in OFFLINE_STEPS:
        assert any(step["command"] in text for text in texts), (
            f"{step['module']}: '{step['command']}' is verified here but no "
            f"longer appears in WORKSHOP.md or WORKSHOP-2H.md")


def test_every_offline_command_still_produces_what_the_guide_promises():
    """Catches the tool being changed away from what the guide shows a room."""
    for step in OFFLINE_STEPS:
        # a step may need state a previous command produced; evidence/ is
        # gitignored, so a fresh clone has no report to cat until the gate runs
        if step.get("setup"):
            _run(step["setup"])
        code, output = _run(step["command"])
        assert code == step["exit_code"], (
            f"{step['module']}: `{step['command']}` exited {code}, "
            f"guide says {step['exit_code']}")
        for expected in step["must_contain"]:
            assert expected in output, (
                f"{step['module']}: the guide promises {expected!r} and the tool "
                f"no longer prints it")


def test_every_metric_the_docs_name_actually_exists():
    """The docs show ILLUSTRATIVE metric blocks – labels trimmed, values chosen
    for the story – so they cannot be matched literally. Metric NAMES can be, and
    that is the half that goes stale: a renamed or invented series sends someone
    to build a dashboard panel that will never match anything.

    This exists because the README briefly claimed
    `resops_tolerated{workload="reporting-db"} 1` when the shipped estate emits 0.
    Same illustration-vs-reality trap the guide test was written for."""
    _, output = _run("python3 -m resops metrics config/estate.yaml")
    real = {line.split("{")[0].split(" ")[0]
            for line in output.splitlines() if line.startswith("resops_")}
    docs = ["README.md", "RESOPS.md", "WORKSHOP.md", "WORKSHOP-2H.md"]
    docs += [d for d in PRIVATE_DOCS if (ROOT / d).exists()]
    for doc in docs:
        for named in set(re.findall(r"\bresops_[a-z_]+\b", (ROOT / doc).read_text())):
            assert named in real, f"{doc} names {named}, which the tool never emits"


def test_every_file_the_guides_point_at_exists():
    """A dead link in a room is a facilitator improvising."""
    for name in LINKED_FILES:
        assert (ROOT / name).exists(), f"{name} is referenced by the guides but missing"


def test_the_published_guides_cross_reference_each_other():
    """Someone landing cold on one published doc must find the others."""
    guide = GUIDE.read_text()
    assert "WORKSHEETS.md" in guide
    assert "WORKSHOP.md" in (ROOT / "WORKSHEETS.md").read_text()


def test_the_published_guides_never_link_to_a_private_doc():
    """A markdown link to a gitignored file is a 404 for everyone who clones.
    The runbook is referred to in prose on purpose, never linked."""
    for doc in ("README.md", "WORKSHOP.md", "WORKSHOP-2H.md", "WORKSHEETS.md",
                "RESOPS.md", "VERIFY.md"):
        text = (ROOT / doc).read_text()
        for private in PRIVATE_DOCS:
            assert f"]({private})" not in text, (
                f"{doc} links to {private}, which is gitignored – that link is "
                f"broken in every clone")


def test_the_guide_never_promises_a_live_step_will_work_offline():
    """A participant on the offline path must never hit a command that needs a
    tenant without the guide having said so first."""
    text = GUIDE.read_text()
    for live_command in ("op climb", "op incident", "op restore", "op backup"):
        if live_command in text:
            assert "LIVE" in text, (
                f"{live_command!r} appears in the guide with no LIVE marker anywhere")

# --------------------------------------------------------------------------- #
# The estate demo's SHAPE, pinned workload by workload.
#
# WHY THIS EXISTS. On 2026-08-12 a new rule at the Scan rung moved identity-svc
# from "blocked at Validate" to "blocked at Scan", and 201 tests stayed green.
# The commands still ran, the exit codes still matched, every substring the guide
# quotes was still printed – and M1's entire lesson had changed, because that
# lesson is not a substring. It is WHICH workload stops WHERE:
#
#   "checkout-api and identity-svc sit on the SAME rung for opposite reasons –
#    one was tested and is contaminated, one was never tested. The rung hides
#    that. The blocked stage names it."
#
# If two workloads stop at the same stage, that paragraph is false and the module
# has no punchline. A substring check cannot see it. This can.
# --------------------------------------------------------------------------- #
ESTATE_LADDER = {
    "payments-api": ("VALIDATED", None),          # promotes, the control
    "checkout-api": ("RECOVERABLE", "Scan"),      # tested, and contaminated
    "identity-svc": ("RECOVERABLE", "Validate"),  # verified, never proven
    "reporting-db": ("PROTECTED", "Detect"),      # last backup failed
    "edge-cache": ("MONITORED", "Recover"),       # SLA missed
    "legacy-batch": ("UNDISCOVERED", "Discover"),  # never onboarded
}


def _parse_ladder(output: str) -> dict:
    """{workload: (state, blocked_stage_or_None)} from the rendered gate output.

    Deliberately parses what a ROOM SEES rather than calling the engine, because
    the thing being protected is the guide's promise about the screen.
    """
    found, current = {}, None
    for line in ANSI.sub("", output).splitlines():
        stripped = line.strip()
        if stripped.startswith("\u25b8 "):
            current = stripped[2:].split()[0]
            continue
        if current and any(s in stripped for s in
                           ("VALIDATED", "RECOVERABLE", "PROTECTED", "MONITORED",
                            "UNDISCOVERED", "DISCOVERED", "TRUSTED")):
            state = next(w for w in stripped.split() if w.isupper() and w.isalpha())
            stage = stripped.split("blocked at ")[1].split()[0] if "blocked at " in stripped else None
            found[current] = (state, stage)
            current = None
    return found


def test_the_estate_demo_stops_each_workload_where_the_guide_says():
    code, output = _run("python3 -m resops gate config/estate.yaml")
    assert code == 1
    actual = _parse_ladder(output)
    assert actual == ESTATE_LADDER, (
        "the estate demo changed shape. M1 teaches WHICH workload stops WHERE, so "
        "a moved rung rewrites the lesson without touching WORKSHOP.md.\n"
        f"  expected {ESTATE_LADDER}\n  actual   {actual}")


def test_the_two_recoverable_workloads_stop_for_DIFFERENT_reasons():
    """M1's punchline, asserted directly. Same rung, different stage. If these two
    ever collapse onto one stage the module loses the point it exists to make."""
    contaminated = ESTATE_LADDER["checkout-api"]
    never_proven = ESTATE_LADDER["identity-svc"]
    assert contaminated[0] == never_proven[0] == "RECOVERABLE"
    assert contaminated[1] != never_proven[1]
    code, output = _run("python3 -m resops gate config/estate.yaml")
    actual = _parse_ladder(output)
    assert actual["checkout-api"][1] != actual["identity-svc"][1]


# --------------------------------------------------------------------------- #
# WORKSHOP-2H.md – the two-hour form.
#
# A second guide is a second drift surface. These bind it to the same rules the
# six-hour guide has had since the beginning, plus three that are specific to
# compressing a day into two hours: the live commands must be the SHORT list, the
# metrics command has an ordering dependency that will bite a fresh clone, and
# the two forms must not silently disagree about what a command prints.
# --------------------------------------------------------------------------- #
TWO_HOUR_LIVE_COMMANDS = (
    "python3 -m resops.operator.op status infra/workloads",
    "python3 -m resops.operator.op gate infra/workloads",
    "python3 -m resops.operator.op incident infra/workloads",
    "python3 -m resops.operator.op backup infra/workloads",
    "python3 -m resops.operator.op threatscan infra/workloads",
    "python3 -m resops.operator.op remediate infra/workloads",
)


def test_the_two_hour_guide_exists_and_says_it_is_two_hours():
    """The Level/Duration/Audience line left the masthead on 2026-08-19 and
    moved into the "Who this is for" list, which is the section that already
    answers the question. DIALECT §3 still requires the start page to state
    level, duration and audience -- it just no longer does it in the hero."""
    text = GUIDE_2H.read_text()
    assert "DURATION         Two hours facilitated" in text
    assert "LEVEL            300-400" in text
    assert "WRITTEN FOR" in text


def test_the_guide_warns_about_the_live_half_before_the_first_live_command():
    """RE-AIMED 2026-08-19, when the per-chapter LIVE badge was removed.

    The old assertion was `"LIVE" in text` -- satisfied by the badge on every
    chapter heading. Those badges are gone, so the guard has to point at what
    replaced them: the Setup page tells a self-paced reader that some of this
    needs a real Azure subscription and a real Commvault tenant, and it has to
    say so BEFORE the first command that needs one. A reader who gets to
    `terraform apply` and only then discovers they need a subscription has
    been failed by the page."""
    text = GUIDE_2H.read_text()
    warned = text.index("run against a real Azure VM")
    first_live = min(text.index(c) for c in (
        "terraform -chdir=infra/workloads apply",
        "python3 -m resops.operator.op"))
    assert warned < first_live, (
        "the guide runs a command needing a tenant before it says one is "
        "needed")
    for prerequisite in ("an Azure subscription", "Commvault Cloud"):
        assert prerequisite in text, (
            f"Setup no longer lists {prerequisite!r}; with the per-chapter "
            f"LIVE badges gone this block is the only warning there is")


def _room_build():
    """The ROOM rendering of the guide. Since the 2026-08 restructure the
    markdown carries the SOLO chapters too (Build, Re-prove, where a lone
    reader runs the drill themselves); the room doctrine below applies to
    what a ROOM participant is actually handed, which is this build."""
    sys.path.insert(0, str(ROOT / "tools"))
    from guide.build import build
    import tempfile, pathlib
    out = pathlib.Path(tempfile.mkdtemp()) / "room.html"
    return build(GUIDE_2H, out, "test-vm", mode="room")


def test_the_room_build_runs_op_restore_NOWHERE():
    """THE LOAD-BEARING ONE.

    `op restore` builds a real Azure VM, needs vCPU quota and waits on a media
    agent slot. It is the most fragile command in the toolkit, and roughly a
    third of the two-hour budget. In a ROOM it runs in PREP and once on the
    facilitator's projector, never on twenty laptops. The SOLO build carries
    it on purpose: one reader, one tenant, their own clock.

    If someone untags the Build or Re-prove chapters to close a perceived
    gap, the room loses its slack and fails at minute 25 for a reason nobody
    planned for."""
    assert "op restore" not in _room_build(), (
        "op restore is in the ROOM build. It belongs in prep. See "
        "FACILITATOR.md's two-hour section for why.")


def test_the_room_build_uses_only_the_six_agreed_live_commands():
    """Scope creep in a two-hour session shows up as extra live commands, each
    with its own queue and its own failure mode. Guarded on the ROOM build:
    the SOLO chapters legitimately add preflight/protect/restore for the
    lone reader who provisions their own lab."""
    found = set(re.findall(
        r"python3 -m resops\.operator\.op ([a-z]+) infra/workloads",
        _room_build()))
    agreed = {c.split()[3] for c in TWO_HOUR_LIVE_COMMANDS}
    unexpected = found - agreed
    assert not unexpected, f"unplanned live commands in the room build: {unexpected}"


def test_the_two_hour_guide_runs_the_estate_gate_BEFORE_metrics():
    """`resops metrics` publishes the LAST run and exits 2 with
    'no run to publish' if there isn't one. evidence/ is gitignored, so on a
    fresh clone the metrics command produces nothing at all.

    Verified by moving evidence/ aside: exit 2, not exit 0. A guide that shows
    metrics without the gate first hands the room an error at beat 6."""
    text = GUIDE_2H.read_text()
    gate = text.index("python3 -m resops gate config/estate.yaml")
    metrics = text.index("python3 -m resops metrics config/estate.yaml")
    assert gate < metrics, (
        "the two-hour guide shows `resops metrics` before `resops gate "
        "config/estate.yaml`. metrics reads the last run; on a fresh clone "
        "there is none and it exits 2.")


def test_both_guides_agree_on_the_verify_script_line_count():
    """Two guides describing the same twenty-five lines must not drift apart.
    The number is checked against the real file by test_verify_contract.py."""
    for g in GUIDES:
        text = g.read_text()
        assert "hirty lines" not in text and "orty lines" not in text, (
            f"{g.name} quotes a stale line count for verify.sh")


def test_no_doc_claims_a_backup_timing_that_was_measured_on_the_wrong_job():
    """A VSA backup produces TWO jobs and both read as "Backup":

        VM Admin Job(Backup)   the PARENT. What POST .../backup returns, so what
                               poll_job polls and what a participant waits for.
        Backup                 the CHILD. Faster, and its id is what the Azure
                               GXMD snapshot NAME embeds.

    Sampling the snapshot names measures the child and understates the wait by
    about 30 seconds. That produced "0.8 min median", then "under 90s in 16 of
    16 jobs", and the next session found five of six real backups exceeding the
    stated maximum.

    Re-measured 2026-08-18 on the parent jobs: 77-134s, median 91s, only 8 of 17
    under 90 seconds. Wall clock for `op backup` end to end: 88-149s over 6 runs.

    This pins the retracted claims out of every doc AND out of the poller, which
    is where they kept getting reseeded from."""
    targets = [ROOT / d for d in ("README.md", "RESOPS.md", "WORKSHOP.md",
                                  "WORKSHOP-2H.md", "VERIFY.md")]
    targets.append(ROOT / "resops/operator/commvault.py")
    targets.append(ROOT / "loop.sh")
    for f in targets:
        if not f.exists():
            continue
        text = f.read_text()
        # SPELLINGS MATTER. The first version of this test listed only
        # "typically 5-15 min" and missed "a 5-15 minute queue is NORMAL" in a
        # guide written the same day, four lines from a command. The walk guard
        # caught that, not this test. So match the FIGURES, not the phrasing.
        for retracted in ("under 90s in 16 of 16", "0.8 min median",
                          "5-15 min", "5 to 15 min", "never exceeded 90s"):
            if retracted not in text:
                continue
            # A retracted figure may be QUOTED anywhere, as the record of what was
            # wrong – that history is worth keeping. What must never happen is it
            # standing alone as if it were current. So the rule is not "never
            # mention it", it is "never mention it without the correction".
            assert "CHILD" in text or "child job" in text, (
                f"{f.name} quotes {retracted!r} with no correction beside it. It "
                f"was measured on the CHILD job, not the parent poll_job polls.")


# --------------------------------------------------------------------------- #
# How long is verify.sh, really.
#
# WHY THIS EXISTS. Five public docs described the same script and gave THREE
# different lengths: "twenty-five lines" (README, RESOPS, WORKSHOP 4.1),
# "seventy lines" (WORKSHOP 5.3 and its adoption ladder), and "20 lines"
# (RESOPS's ladder). Every one of them was written by someone who had counted
# something real -- 25 is the non-blank non-comment lines, ~70 is the listing
# -- and WORKSHOP.md contradicted itself twice in one file, with the wrong
# number sitting in the paragraph directly under the grep that prints the
# right one on screen.
#
# The guard that existed banned the SPELLINGS "hirty lines" and "orty lines",
# which is a rule written against the last number that was wrong rather than
# against the file. It could never have caught "twenty-five". So this one
# reads the script, counts it, and rejects any claim the file contradicts.
# --------------------------------------------------------------------------- #
CLOUD_INIT = ROOT / "infra/modules/azure-vm/cloud-init.yaml"

_NUMBER_WORDS = {
    "ten": 10, "twenty": 20, "twenty-five": 25, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}


def _verify_sh_length() -> int:
    """The length of verify.sh as a participant sees it: the listing that
    `grep -A 80 'path: /opt/app/verify.sh'` puts on their screen."""
    body = CLOUD_INIT.read_text().split("path: /opt/app/verify.sh", 1)[1]
    body = body.split("content: |", 1)[1]
    marker = "\n      exit 0\n"
    return len(body[:body.index(marker) + len(marker)].strip("\n").split("\n"))


def test_no_doc_quotes_a_verify_sh_length_the_script_contradicts():
    actual = _verify_sh_length()
    claim = re.compile(r"\b([0-9]{1,3}|" + "|".join(_NUMBER_WORDS) + r")[ -]lines\b",
                       re.IGNORECASE)
    docs = ["README.md", "RESOPS.md", "WORKSHOP.md", "WORKSHOP-2H.md", "VERIFY.md"]
    docs += [d for d in PRIVATE_DOCS if (ROOT / d).exists()]
    for doc in docs:
        text = (ROOT / doc).read_text()
        for m in claim.finditer(text):
            window = text[max(0, m.start() - 200):m.end() + 200].lower()
            if "verify.sh" not in window and "of shell" not in window \
                    and "five checks" not in window:
                continue        # some other file's line count, not ours
            # VERIFY.md teaches people to WRITE one: "Twenty lines is a good
            # target" is advice about the reader's script, not a claim about
            # ours, and the two must not be confused. Prescriptive sentences
            # are exempt; descriptive ones are what this guards.
            sentence = text[max(0, text.rfind(".", 0, m.start()) + 1):
                            m.end() + 120].lower()
            if "target" in sentence or "aim for" in sentence:
                continue
            token = m.group(1).lower()
            stated = _NUMBER_WORDS.get(token, int(token) if token.isdigit() else None)
            assert stated is not None and abs(stated - actual) <= 10, (
                f"{doc} says verify.sh is {m.group(0)!r}; the script in "
                f"cloud-init.yaml is {actual} lines. Two numbers for one file "
                f"means one of them is lying and a room cannot tell which.")


def test_metallic_appears_only_inside_the_full_product_name():
    """The Commvault editorial guide's usage list is explicit:

        "Commvault(R) Cloud, powered by Metallic(R) AI  (Use this full
         description, including registered trademarks, for the first usage
         when space allows, then use Commvault Cloud upon subsequent usage)"

    So Metallic is not banned -- it is part of the product's full name. What
    IS wrong is naming Metallic as the PLATFORM, because Metallic became
    Commvault Cloud in November 2023 and a reader new to Commvault would go
    looking for something that no longer exists under that name. The tenant
    endpoint in this repository is still a metallic.io host; that is legacy
    infrastructure naming and must never reach a participant page."""
    for doc in ("WORKSHOP-2H.md", "WORKSHOP.md"):
        text = (ROOT / doc).read_text()
        for hit in re.finditer(r"Metallic", text):
            window = text[hit.start():hit.start() + 40]
            assert window.startswith("Metallic\u00ae AI") or \
                   window.startswith("Metallic AI"), (
                f"{doc} names Metallic outside the full product name: "
                f"{text[max(0, hit.start()-40):hit.start()+40]!r}. The "
                f"platform is Commvault Cloud.")
        assert "metallic.io" not in text, f"{doc} exposes the legacy endpoint host"


def test_the_guide_names_the_capabilities_it_makes_participants_use():
    """ENABLEMENT, PINNED.

    The guide demonstrated Air Gap Protect and Threat Scan and, until
    2026-08-19, never named either. A participant new to Commvault finished
    the workshop able to say "resilience gap" and unable to name a single
    capability they had just used, which is the wrong way round for a day
    whose purpose is enablement: the concepts are available in any blog
    post, the capability names are what they need in order to ask for
    anything internally.

    The rule stays "demo it, then name it" -- these must appear AFTER the
    command that uses them, never in the framing."""
    text = (ROOT / "WORKSHOP-2H.md").read_text()
    lower = text.lower()          # casing is presentation; the NAME is the point
    for capability in ("air gap protect", "threat scan", "command center",
                       "protection plan"):
        assert capability in lower, f"the guide never names {capability}"
    # A CAPABILITY is named only after the command that uses it. The
    # PLATFORM and the CONSOLE are exempt: a reader has to set both up
    # before chapter 1, so naming them in orientation is practical rather
    # than promotional.
    first_backup = lower.index("op backup infra/workloads")
    first_scan = lower.index("op threatscan infra/workloads")
    assert lower.index("air gap protect") > first_backup, (
        "Air Gap Protect is named before the participant has used it")
    assert lower.index("threat scan") > first_scan, (
        "Threat Scan is named before the participant has run it")
