"""The read/write boundary as a CHECK, not a convention.

`resops` (the top-level modules + assurance/) is the read-only star: it reads the
ladder, judges the gate, and writes evidence files – but it must never shell out
(az/terraform) or depend on the write lane (resops.operator). That guarantee is
what makes resops safe to drop in CI. Here we enforce it by scanning imports, so a
stray `import subprocess` or `from .operator …` in the read path fails the suite
instead of silently eroding the property.
"""
from pathlib import Path

RESOPS = Path(__file__).resolve().parent.parent / "resops"

# The read-only star = resops/*.py + resops/assurance/*.py. NOT resops/operator/ –
# that's the write lane, where shelling out and mutation rightly live.
READ_ONLY = sorted(RESOPS.glob("*.py")) + sorted((RESOPS / "assurance").glob("*.py"))


def _import_lines(path: Path) -> str:
    return "\n".join(ln for ln in path.read_text().splitlines()
                     if ln.strip().startswith(("import ", "from ")))


def test_read_only_star_never_shells_out():
    # subprocess = az / terraform – the write lane's tools, never the star's.
    offenders = [p.name for p in READ_ONLY if "subprocess" in _import_lines(p)]
    assert not offenders, f"read-only resops must not import subprocess: {offenders}"


def test_read_only_star_does_not_depend_on_the_write_lane():
    # The dependency arrow points one way: operator -> resops, never resops -> operator.
    offenders = [p.name for p in READ_ONLY if "operator" in _import_lines(p)]
    assert not offenders, f"read-only resops must not import the operator write lane: {offenders}"


# --------------------------------------------------------------------------- #
# The HTTP half of the same guarantee.
#
# The two tests above scan IMPORTS. They would not notice a `.post()` appearing in
# reads.py tomorrow, and "this physically cannot mutate your environment" is the
# single property a platform team adopts this on. A guarantee with no test is a
# convention, and conventions are what this repo keeps watching rot.
#
# Exactly ONE non-GET call is allowed in the read-only star, and it is named here
# so that adding a second is a decision someone has to make in the open.
# --------------------------------------------------------------------------- #
MUTATING = (".post(", ".put(", ".delete(", ".patch(")

# file -> the one sanctioned mutating call, and why it does not touch the tenant.
SANCTIONED = {
    "client.py": "_renew() POSTs V4/AccessToken/Renew – trades a refresh token "
                 "for a fresh access token. An auth call against our own session; "
                 "it creates, changes and deletes nothing in the environment.",
}


def _mutating_calls(path):
    return [f"{path.name}:{i}" for i, ln in enumerate(path.read_text().splitlines(), 1)
            if any(v in ln for v in MUTATING)]


def test_the_read_only_star_makes_no_UNSANCTIONED_mutating_http_call():
    """Add a .post/.put/.delete/.patch to the read path and this fails.

    Not a style rule. `resops` is dropped into other people's CI on the promise
    that it cannot change anything it looks at."""
    offenders = []
    for p in READ_ONLY:
        calls = _mutating_calls(p)
        if calls and p.name not in SANCTIONED:
            offenders += calls
    assert not offenders, (
        f"read-only resops gained a mutating HTTP call: {offenders}. "
        f"If it is genuinely safe, add it to SANCTIONED with the reason.")


def test_the_one_sanctioned_exception_has_not_multiplied():
    """client.py is allowed ONE. Two would mean the exception became a habit."""
    calls = _mutating_calls(RESOPS / "client.py")
    assert len(calls) == 1, (
        f"client.py should make exactly one mutating call (the token renewal); "
        f"found {len(calls)}: {calls}")
