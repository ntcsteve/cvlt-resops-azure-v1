#!/usr/bin/env python3
"""Build the participant HTML from WORKSHOP-2H.md.

  python3 tools/guide/build.py --out dist/guide.html --codename osprey-vm01

One self-contained file per codename: opens from file:// with the network
off. Content is authored ONLY in WORKSHOP-2H.md; images live beside it in
images/ and are inlined as data URIs. Commands are identical for every
participant; the build refuses a codename that leaks into a command block.
"""

import argparse
import base64
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from guide import parser, render  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent
ASSETS = Path(__file__).resolve().parent / "assets"
ICONS = ASSETS / "icons"

CSS_ORDER = ["tokens.css", "base.css", "components.css", "layout.css"]
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp"}
IMAGE_WARN_BYTES = 300 * 1024


def inline_images(nodes_flat, md_dir):
    """Every ![caption](path) becomes a data URI. Missing file = hard error;
    big file = warning; unreferenced file in images/ = warning."""
    refs = [node[2] for node in nodes_flat if node[0] == "fig"]
    images = {}
    for ref in refs:
        path = md_dir / ref
        if not path.is_file():
            raise SystemExit(f"image not found: {ref} (looked in {path})")
        data = path.read_bytes()
        if len(data) > IMAGE_WARN_BYTES:
            print(f"warning: {ref} is {len(data) // 1024}KB; compress it "
                  "or the one-file guide gets heavy", file=sys.stderr)
        mime = MIME.get(path.suffix.lower())
        if not mime:
            raise SystemExit(f"unsupported image type: {ref}")
        images[ref] = f"data:{mime};base64," + \
            base64.b64encode(data).decode("ascii")
    img_dir = md_dir / "images"
    if img_dir.is_dir():
        for f in sorted(img_dir.iterdir()):
            if f.is_file() and f"images/{f.name}" not in refs:
                print(f"warning: images/{f.name} is not referenced by "
                      "WORKSHOP-2H.md", file=sys.stderr)
    return images


def inline_icons(needed):
    """Official Commvault icons from assets/icons/, inlined as data URIs.

    Data URI rather than inline markup because the source files share ids
    (`In_progress`, `COMPLETED_ICONS`) and a `.cls-1` class, so pasting
    several into one document produces duplicate ids and colliding CSS.
    They are the MIDNIGHT variants: the color budget reserves crocus for
    interaction, and an icon is content."""
    out = {}
    for name in sorted(needed):
        path = ICONS / f"{name}.svg"
        if not path.is_file():
            raise SystemExit(
                f"unknown icon @{name}: expected "
                f"{path.relative_to(REPO)}. Official icons only.")
        raw = path.read_bytes()
        out[name] = "data:image/svg+xml;base64," + \
            base64.b64encode(raw).decode("ascii")
    if ICONS.is_dir():
        for f in sorted(ICONS.glob("*.svg")):
            if f.stem not in needed:
                print(f"warning: assets/icons/{f.name} is not used by any "
                      "@icon row", file=sys.stderr)
    return out


def check_expected_output(workshop):
    """Every command must be followed by a ✓ expected-output box before the
    next command begins. "Never let someone get stuck" is a build rule,
    not authoring discipline. ✗ recovery rows stay author judgment: not
    every command has a failure mode worth inventing prose for."""
    def fail(cmd, where):
        first = cmd.split("\n")[0]
        raise SystemExit(
            f"{where}: command `{first}` has no ✓ expected-output box "
            "after it. Every command ships with what the participant "
            "should see, or the guide does not build. "
            "See tools/guide/DIALECT.md.")

    def scan(nodes, where):
        pending = None
        for node in nodes:
            if node[0] == "cmd":
                if pending is not None:
                    fail(pending, where)
                pending = node[1]
            elif node[0] == "diag":
                if any(r["glyph"] == "✓" for r in node[1]):
                    pending = None
        if pending is not None:
            fail(pending, where)

    scan(workshop["overview"], "Overview page")
    scan(workshop["setup"], "Setup page")
    for ch in workshop["chapters"]:
        scan(ch["body"], f"chapter {ch['num']} ({ch['name']})")
    scan(workshop["close"], "close page")


def attestation_facts(md_text):
    """Where the ```attestation block's numbers come from.

    Read from the machinery that ENFORCES the claim, never from prose: the
    offline step list that pytest re-runs, and the walk record that the walk
    guard defends. A hand-written provenance line is the failure this whole
    block exists to avoid.

    DETERMINISM. dist/ is committed and byte-compared, so nothing here may
    change without a source change. No elapsed-days count, no HEAD sha. The
    walk record's own date and commit are stable until somebody walks again,
    which is precisely the event that should move this text.
    """
    steps = REPO / "tests" / "test_workshop_guide.py"
    covered = []
    if steps.is_file():
        src = steps.read_text(encoding="utf-8")
        # "command": "..."  and the parenthesized multi-line form
        for m in re.finditer(r'"command":\s*\(?\s*((?:"[^"]*"\s*)+)\)?', src):
            covered.append("".join(re.findall(r'"([^"]*)"', m.group(1))))

    cmds = [c.strip() for c in re.findall(r"```bash\n(.*?)\n```", md_text, re.S)]
    verified = [c for c in cmds if c in covered]

    # THREE buckets, not two. Subtracting verified from total would count the
    # `cd`/`source .venv` block as needing an Azure subscription, which is the
    # small kind of untruth this whole block exists to prevent.
    LIVE = ("terraform ", "az ", "resops.operator.op ")
    live = [c for c in cmds if c not in verified
            and any(k in c for k in LIVE)]
    local = [c for c in cmds if c not in verified and c not in live]

    facts = {"total": len(cmds), "verified": len(verified),
             "live": len(live), "local": len(local)}

    record = REPO / "tests" / "workshop_walk.json"
    if record.is_file():
        rec = json.loads(record.read_text(encoding="utf-8"))
        facts["walked_at"] = rec.get("walked_at")
        facts["walked_commit"] = rec.get("walked_commit")
    return facts


def check_offline(page):
    """The whole point is a file that works with the network off."""
    external = re.findall(r'(?:src|href)="(https?://[^"]+)"', page)
    if external:
        raise SystemExit(f"external references would break offline: "
                         f"{external[:3]}")


def check_codename(page, codename):
    for m in re.finditer(r"<pre><code>(.*?)</code></pre>", page, re.S):
        if codename in m.group(1):
            raise SystemExit(
                "codename leaked into a command block; commands must be "
                "identical for every participant")


def build(md_path, out_path, codename=None, mode="solo"):
    text = Path(md_path).read_text(encoding="utf-8")
    if codename:
        text = text.replace("<your-codename>", codename)

    nodes = parser.parse(text)
    workshop = parser.group(nodes)
    parser.check(workshop)
    check_expected_output(workshop)

    images = inline_images(nodes, Path(md_path).resolve().parent)
    needed = {r["icon"] for n in nodes if n[0] == "deflist"
              for r in n[1] if r.get("icon")}
    needed |= {n[4] for n in nodes if n[0] == "chapter" and n[4]}
    icons = inline_icons(needed)
    css = "\n".join((ASSETS / name).read_text(encoding="utf-8")
                    for name in CSS_ORDER)
    js = (ASSETS / "app.js").read_text(encoding="utf-8")
    brand = {
        name: "data:image/png;base64," + base64.b64encode(
            (ASSETS / f"brand-{name}.png").read_bytes()).decode("ascii")
        for name in ("mark", "wordmark")
    }
    brand["favicon"] = brand["mark"]      # the tab gets the hexagon too

    attest = attestation_facts(text)
    page = render.render_document(workshop, css, js, images, brand, mode,
                                  icons, attest)
    check_offline(page)
    if codename:
        check_codename(page, codename)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return page


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--md", default=str(REPO / "WORKSHOP-2H.md"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--codename", default=None,
                    help="participant codename; appears in the landing chip "
                         "and expected-output boxes, never in a command")
    ap.add_argument("--mode", default="solo", choices=("solo", "room"),
                    help="solo renders every chapter; room renders "
                         "SOLO-tagged chapters as inherited stubs")
    args = ap.parse_args()
    page = build(args.md, args.out, args.codename, args.mode)
    n = page.count('<section class="page"')
    print(f"wrote {args.out} ({len(page) // 1024}KB, {n} pages, "
          f"codename={args.codename or 'placeholder'})")


if __name__ == "__main__":
    main()
