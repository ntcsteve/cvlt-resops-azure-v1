"""The read/write boundary as a CHECK, not a convention.

`resops` (the top-level modules + assurance/) is the read-only star: it reads the
ladder, judges the gate, and writes evidence files — but it must never shell out
(az/terraform) or depend on the write lane (resops.operator). That guarantee is
what makes resops safe to drop in CI. Here we enforce it by scanning imports, so a
stray `import subprocess` or `from .operator …` in the read path fails the suite
instead of silently eroding the property.
"""
from pathlib import Path

RESOPS = Path(__file__).resolve().parent.parent / "resops"

# The read-only star = resops/*.py + resops/assurance/*.py. NOT resops/operator/ —
# that's the write lane, where shelling out and mutation rightly live.
READ_ONLY = sorted(RESOPS.glob("*.py")) + sorted((RESOPS / "assurance").glob("*.py"))


def _import_lines(path: Path) -> str:
    return "\n".join(ln for ln in path.read_text().splitlines()
                     if ln.strip().startswith(("import ", "from ")))


def test_read_only_star_never_shells_out():
    # subprocess = az / terraform — the write lane's tools, never the star's.
    offenders = [p.name for p in READ_ONLY if "subprocess" in _import_lines(p)]
    assert not offenders, f"read-only resops must not import subprocess: {offenders}"


def test_read_only_star_does_not_depend_on_the_write_lane():
    # The dependency arrow points one way: operator -> resops, never resops -> operator.
    offenders = [p.name for p in READ_ONLY if "operator" in _import_lines(p)]
    assert not offenders, f"read-only resops must not import the operator write lane: {offenders}"
