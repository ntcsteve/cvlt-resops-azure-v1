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
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from guide import parser, render  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent
ASSETS = Path(__file__).resolve().parent / "assets"

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

    scan(workshop["setup"], "Start page")
    for act in workshop["acts"]:
        for beat in act["beats"]:
            scan(beat["body"], f"beat {beat['num']} ({beat['name']})")
    scan(workshop["close"], "close page")


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


def build(md_path, out_path, codename=None):
    text = Path(md_path).read_text(encoding="utf-8")
    if codename:
        text = text.replace("<your-codename>", codename)

    nodes = parser.parse(text)
    workshop = parser.group(nodes)
    parser.check(workshop)
    check_expected_output(workshop)

    images = inline_images(nodes, Path(md_path).resolve().parent)
    css = "\n".join((ASSETS / name).read_text(encoding="utf-8")
                    for name in CSS_ORDER)
    js = (ASSETS / "app.js").read_text(encoding="utf-8")
    brand = {
        name: "data:image/png;base64," + base64.b64encode(
            (ASSETS / f"brand-{name}.png").read_bytes()).decode("ascii")
        for name in ("mark", "wordmark")
    }

    page = render.render_document(workshop, codename, css, js, images, brand)
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
                    help="participant codename; appears in the topbar chip "
                         "and expected-output boxes, never in a command")
    args = ap.parse_args()
    page = build(args.md, args.out, args.codename)
    n = page.count('<section class="page"')
    print(f"wrote {args.out} ({len(page) // 1024}KB, {n} pages, "
          f"codename={args.codename or 'placeholder'})")


if __name__ == "__main__":
    main()
