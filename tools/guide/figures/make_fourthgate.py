"""Compose images/fourth-gate.svg: the Overview's opening frame, completed.

The Overview shows delivery engineered and recovery as a handoff. This is
the finished picture: both loops solid, both gated, both read by CI as
exit codes. Colors mirror tools/guide/assets/tokens.css (crocus #844896
kickers, the yes shade #30881c, muted #707391, ink #00053b, fog #eaeaea);
change them there first.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
YES, MUTED, INK, FOG, CROCUS = "#30881c", "#707391", "#00053b", "#eaeaea", "#844896"
F = "Arial, Helvetica, sans-serif"

out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 278" '
       'width="960" height="278" role="img" aria-label="Two loops. Delivery: '
       'code, build, deploy, observe, respond, already gated by tests, scans, '
       'lint and plan. Recovery: discover, protect, detect, recover, scan, '
       'validate, gated by one required check that exits 0 or 1 on every '
       'change.">',
       '  <!-- Colors mirror tools/guide/assets/tokens.css: crocus #844896 on',
       '       the row kickers, the yes shade #30881c on the fourth gate,',
       '       muted #707391, ink #00053b, fog #eaeaea. Change them there',
       '       first. -->',
       '  <rect width="960" height="278" fill="#ffffff"/>']

def row(label, y, names, x0=150, x1=930):
    n = len(names)
    gap = 24
    w = (x1 - x0 - (n - 1) * gap) // n
    out.append(f'<text x="40" y="{y+27}" font-family="{F}" font-size="12" '
               f'font-weight="bold" letter-spacing="1" '
               f'fill="{CROCUS}">{label}</text>')
    for i, name in enumerate(names):
        x = x0 + i * (w + gap)
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="44" rx="6" '
                   f'fill="#ffffff" stroke="{FOG}" stroke-width="1.5"/>')
        out.append(f'<text x="{x+w//2}" y="{y+27}" text-anchor="middle" '
                   f'font-family="{F}" font-size="14" fill="{INK}">{name}</text>')
        if i:
            ax = x - gap
            out.append(f'<line x1="{ax+3}" y1="{y+22}" x2="{x-8}" y2="{y+22}" '
                       f'stroke="{MUTED}" stroke-width="1.2"/>')
            out.append(f'<path d="M {x-8} {y+18} L {x-1} {y+22} L {x-8} '
                       f'{y+26} Z" fill="{MUTED}"/>')
    return x0, x1

def bracket(x0, x1, y, text, color):
    out.append(f'<path d="M {x0} {y} L {x0} {y+9} L {x1} {y+9} L {x1} {y}" '
               f'fill="none" stroke="{color}" stroke-width="1.5"/>')
    out.append(f'<text x="{(x0+x1)//2}" y="{y+30}" text-anchor="middle" '
               f'font-family="{F}" font-size="13" fill="{color}">{text}</text>')

row("DELIVERY", 24, ["Code", "Build", "Deploy", "Observe", "Respond"])
bracket(150, 930, 78, "gated already: tests, security scans, lint, "
        "infrastructure plan", MUTED)
row("RECOVERY", 142, ["Discover", "Protect", "Detect", "Recover", "Scan",
                      "Validate"])
bracket(150, 930, 196, "the fourth gate: one required check, exit 0 or 1, "
        "on every change", YES)

out.append("</svg>")
path = REPO / "images" / "fourth-gate.svg"
path.write_text("\n".join(out) + "\n")
print(f"wrote {path} ({path.stat().st_size} bytes)")
