"""Compose images/evidence-chain.svg: one crosswalk row, traced to the
command that ran. The section is called "The evidence underneath" and this
is that phrase drawn: the claim on top, the evidence stacked underneath.

Every string is real executed output (report.md from the estate gate,
verify.sh's verdict line). Colors mirror tools/guide/assets/tokens.css
(the yes shade #30881c, muted #707391, ink #00053b, fog #eaeaea); change
them there first. Typography teaches: the top box speaks the auditor's
language in Arial, everything below the dashed link is a machine artifact
in mono.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
YES, MUTED, INK, FOG = "#30881c", "#707391", "#00053b", "#eaeaea"
F = "Arial, Helvetica, sans-serif"
FM = "'SF Mono', Menlo, Consolas, monospace"

BX, BW = 250, 460          # box column
LX, RX = 226, 734          # left labels right-aligned, right labels left
CX = 480                   # arrow center

out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 568" '
       'width="960" height="568" role="img" aria-label="One crosswalk row '
       'traced downward: a DORA, NIST and APRA reference rests on a report '
       'capability, which rests on the gate finding, which rests on the '
       'attestation the drill wrote, which rests on verify.sh, the command '
       'that ran.">',
       '  <!-- Colors mirror tools/guide/assets/tokens.css: the yes shade',
       '       #30881c on verified links, muted #707391 on the indicative',
       '       one, ink #00053b, fog #eaeaea. Change them there first. -->',
       '  <rect width="960" height="568" fill="#ffffff"/>']

def box(y, h, who, right, lines):
    out.append(f'<rect x="{BX}" y="{y}" width="{BW}" height="{h}" rx="6" '
               f'fill="#ffffff" stroke="{FOG}" stroke-width="1.5"/>')
    out.append(f'<text x="{LX}" y="{y+h//2+5}" text-anchor="end" '
               f'font-family="{F}" font-size="13" fill="{MUTED}">{who}</text>')
    for i, r in enumerate(right):
        out.append(f'<text x="{RX}" y="{y+h//2-len(right)*9+14+i*18}" '
                   f'font-family="{F}" font-size="12.5" fill="{MUTED}">{r}</text>')
    n = len(lines)
    for i, (txt, mono, extra) in enumerate(lines):
        fam, size = (FM, 13) if mono else (F, 14)
        yy = y + h // 2 + 5 + (i - (n - 1) / 2) * 20
        out.append(f'<text x="{CX}" y="{yy:.0f}" text-anchor="middle" '
                   f'font-family="{fam}" font-size="{size}" fill="{INK}"'
                   f'{extra}>{txt}</text>')

def link(y_bot, y_top, label, dashed=False):
    color = MUTED if dashed else YES
    dash = ' stroke-dasharray="5 4"' if dashed else ""
    out.append(f'<line x1="{CX}" y1="{y_bot}" x2="{CX}" y2="{y_top+11}" '
               f'stroke="{color}" stroke-width="1.5"{dash}/>')
    out.append(f'<path d="M {CX-5} {y_top+12} L {CX} {y_top+1} '
               f'L {CX+5} {y_top+12} Z" fill="{color}"/>')
    out.append(f'<text x="{CX+16}" y="{(y_bot+y_top)//2+9}" '
               f'font-family="{F}" font-size="13" fill="{color}">{label}</text>')

# top to bottom: regime · capability · gate · attestation · the command
box(24, 64, "the auditor", ["a yaml pack:", "data, not code"], [
    ("DORA Art. 11/12 · NIST CP-4, CP-9(1)", False, ""),
    ("APRA CPS 230 scenario &amp; business continuity testing", False, "")])
link(152, 88, "indicative mapping · the one soft link", dashed=True)
box(152, 48, "the report", ["report.md"], [
    ("CAP-RESTORE-TESTED", True, "")])
link(256, 200, "this run&#8217;s finding")
box(256, 64, "the gate", ["exit 0 / 1"], [
    ("validate PASS", True, ""),
    ("recovery proven &#183; job 884730", True, "")])
link(376, 320, "reads the attestation the drill wrote")
box(376, 64, "the drill", ["hash-chained", "history.jsonl"], [
    ('<tspan fill="{}">OK:</tspan> code intact, baseline present, '
     '3 customer records,'.format(YES), True, ""),
    ("no encryption markers, write/read verified", True, "")])
link(496, 440, "ran inside the restored copy")
# Chapter NAME, not number: the room build renumbers chapters, so a number
# is wrong for half the audience while the name is stable in both builds.
box(496, 48, "the app team", ["you read it in", "Reading the Proof"], [
    ("verify.sh &#183; about 70 lines anyone can read", True, "")])

out.append("</svg>")
path = REPO / "images" / "evidence-chain.svg"
path.write_text("\n".join(out) + "\n")
print(f"wrote {path} ({path.stat().st_size} bytes)")
