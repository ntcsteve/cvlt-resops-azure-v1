"""Compose images/verdict-trail.svg: the workshop's thesis as one artifact.

Four verdicts, three causes. Colors mirror tools/guide/assets/tokens.css
(--yes #30881c / --yes-tint #f3faf1, --no #db2961 / --no-tint #fdf2f5,
muted #707391); change them there first.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
YES, YES_T = "#30881c", "#f3faf1"
NO, NO_T = "#db2961", "#fdf2f5"
MUTED, INK = "#707391", "#00053b"
F = "Arial, Helvetica, sans-serif"
FM = "'SF Mono', Menlo, Consolas, monospace"

PILL_W, PILL_H, GAP, Y = 130, 56, 100, 40
XS = [70, 300, 530, 760]

def pill(x, verdict, cmd):
    good = verdict == "PROMOTE"
    fill, color = (YES_T, YES) if good else (NO_T, NO)
    return (
        f'<rect x="{x}" y="{Y}" width="{PILL_W}" height="{PILL_H}" '
        f'rx="{PILL_H//2}" fill="{fill}" stroke="{color}" stroke-width="1.5"/>'
        f'<text x="{x+PILL_W//2}" y="{Y+35}" text-anchor="middle" '
        f'font-family="{F}" font-size="16" font-weight="bold" '
        f'letter-spacing="1.5" fill="{color}">{verdict}</text>'
        f'<text x="{x+PILL_W//2}" y="{Y+78}" text-anchor="middle" '
        f"font-family=\"{FM}\" font-size=\"12.5\" fill=\"{MUTED}\">{cmd}</text>")

def cause(x1, x2, top, bottom):
    mid = (x1 + x2) // 2
    y = Y + PILL_H // 2
    return (
        f'<line x1="{x1}" y1="{y}" x2="{x2-11}" y2="{y}" stroke="{INK}" '
        f'stroke-width="1.5"/>'
        f'<path d="M {x2-11} {y-5} L {x2} {y} L {x2-11} {y+5} Z" fill="{INK}"/>'
        f'<text x="{mid}" y="{Y+96}" text-anchor="middle" font-family="{F}" '
        f'font-size="13" fill="{INK}">{top}</text>'
        f'<text x="{mid}" y="{Y+114}" text-anchor="middle" font-family="{F}" '
        f'font-size="13" fill="{INK}">{bottom}</text>')

parts = [
    pill(XS[0], "PROMOTE", "op gate"),
    pill(XS[1], "HOLD", "op gate"),
    pill(XS[2], "HOLD", "op threatscan"),
    pill(XS[3], "PROMOTE", "op gate"),
    cause(XS[0]+PILL_W, XS[1], "you took", "a backup"),
    cause(XS[1]+PILL_W, XS[2], "something", "looked inside"),
    cause(XS[2]+PILL_W, XS[3], "you", "re-proved it"),
]

svg = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 175" '
    'width="960" height="175" role="img" aria-label="Four verdicts over two '
    'hours: PROMOTE, then HOLD after a backup, then HOLD after something '
    'looked inside, then PROMOTE after re-proving it.">\n'
    '  <!-- Colors mirror tools/guide/assets/tokens.css: the yes shade\n'
    '       #30881c on #f3faf1, the no shade #db2961 on #fdf2f5, muted\n'
    '       #707391, ink #00053b. Change them there first. (A CSS variable\n'
    '       name cannot appear here: XML forbids a double hyphen inside a\n'
    '       comment.) -->\n'
    '  <rect width="960" height="175" fill="#ffffff"/>\n  '
    + "\n  ".join(parts) + "\n</svg>\n")

out = REPO / "images" / "verdict-trail.svg"
out.write_text(svg)
print(f"wrote {out} ({out.stat().st_size} bytes)")
