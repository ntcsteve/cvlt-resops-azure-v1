"""Compose images/three-planes.svg from the three official Commvault icons.

Icons are embedded as base64 data URIs because the source files share ids
and a .cls-1 class (see DIALECT §7) and would collide if inlined as markup.
Colors mirror tools/guide/assets/tokens.css; change them there first.
"""
import base64
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ICONS = REPO / "tools/guide/assets/icons"

def icon(name):
    raw = (ICONS / f"{name}.svg").read_bytes()
    return "data:image/svg+xml;base64," + base64.b64encode(raw).decode()

INK, LINE, CROCUS, NO, MUTED = "#00053b", "#eaeaea", "#844896", "#db2961", "#707391"
F = "Arial, Helvetica, sans-serif"

def card(x, kicker, icon_uri, lines):
    body = [
        f'<text x="{x+120}" y="52" text-anchor="middle" font-family="{F}" '
        f'font-size="13" font-weight="bold" letter-spacing="1" '
        f'fill="{CROCUS}">{kicker}</text>',
        f'<rect x="{x}" y="66" width="240" height="216" rx="8" fill="#ffffff" '
        f'stroke="{LINE}" stroke-width="1.5"/>',
        f'<image x="{x+98}" y="86" width="44" height="44" href="{icon_uri}"/>',
    ]
    for i, (txt, bold) in enumerate(lines):
        weight = ' font-weight="bold"' if bold else ""
        fill = INK if bold else MUTED
        body.append(
            f'<text x="{x+120}" y="{162+i*26}" text-anchor="middle" '
            f'font-family="{F}" font-size="14"{weight} fill="{fill}">{txt}</text>')
    return "\n  ".join(body)

def arrow(x1, x2, y, above, below):
    # The gap between cards is 90px; a one-line label overflows the card
    # borders, so the label splits above and below the shaft.
    mid = (x1 + x2) // 2
    return (
        f'<line x1="{x1}" y1="{y}" x2="{x2-12}" y2="{y}" stroke="{INK}" '
        f'stroke-width="1.5"/>'
        f'<path d="M {x2-12} {y-5} L {x2} {y} L {x2-12} {y+5} Z" fill="{INK}"/>'
        f'<text x="{mid}" y="{y-12}" text-anchor="middle" '
        f'font-family="{F}" font-size="13" fill="{MUTED}">{above}</text>'
        f'<text x="{mid}" y="{y+24}" text-anchor="middle" '
        f'font-family="{F}" font-size="13" fill="{MUTED}">{below}</text>')

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 400"
     width="960" height="400" role="img"
     aria-label="The three planes: production, recovery, isolated. The attacker reaches the workload and never the copies.">
  <!-- Colors mirror tools/guide/assets/tokens.css: ink #00053b, line #eaeaea,
       crocus #844896 (kicker role), rose AA shade #db2961 (the X, a verdict),
       muted #707391. Icons: official Commvault set, Midnight variant. -->
  <rect width="960" height="400" fill="#ffffff"/>
  {card(30, "PRODUCTION PLANE", icon("cloud-server"), [
      ("your VM", True), ("no public IP", False), ("no open ports", False),
      ("no way to log in", False)])}
  {card(360, "RECOVERY PLANE", icon("secure-storage"), [
      ("AIR GAP PROTECT", True), ("immutable copies", False),
      ("service-held keys", False), ("nothing reaches back", False)])}
  {card(690, "ISOLATED PLANE", icon("vm-restore"), [
      ("restored copy", True), ("verified from", False),
      ("the inside,", False), ("then deleted", False)])}
  {arrow(270, 360, 174, "agent", "snapshot")}
  {arrow(600, 690, 174, "restore", "drill")}
  <line x1="150" y1="336" x2="150" y2="290" stroke="{NO}" stroke-width="1.5"/>
  <path d="M 145 294 L 150 282 L 155 294 Z" fill="{NO}"/>
  <text x="150" y="356" text-anchor="middle" font-family="{F}" font-size="14"
        font-weight="bold" fill="{INK}">attacker</text>
  <line x1="196" y1="350" x2="440" y2="350" stroke="{NO}" stroke-width="1.5"
        stroke-dasharray="5 4"/>
  <text x="458" y="355" font-family="{F}" font-size="17" font-weight="bold"
        fill="{NO}">&#10007;</text>
  <text x="482" y="355" font-family="{F}" font-size="14" fill="{MUTED}">no
    path from the VM to the copies, ever</text>
</svg>
'''

out = REPO / "images" / "three-planes.svg"
out.parent.mkdir(exist_ok=True)
out.write_text(svg)
print(f"wrote {out} ({out.stat().st_size} bytes)")
