"""Compose images/proof-timeline.svg: why a backup killed the proof.

An attestation is a claim about one recovery point; the new point sits
outside its reach. Colors mirror tools/guide/assets/tokens.css (the yes
shade #30881c, the no shade #db2961, muted #707391, ink #00053b, fog
#eaeaea); change them there first.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
YES, NO, MUTED, INK, FOG = "#30881c", "#db2961", "#707391", "#00053b", "#eaeaea"
F = "Arial, Helvetica, sans-serif"

AXIS_Y = 96
P1, P2 = 280, 660

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 230"
     width="960" height="230" role="img"
     aria-label="Two recovery points on a time axis. The attestation covers
point 1 and nothing after it; point 2, the backup you just took, is outside
its reach, so the gate holds.">
  <!-- Colors mirror tools/guide/assets/tokens.css: the yes shade #30881c,
       the no shade #db2961, muted #707391, ink #00053b, fog #eaeaea.
       Change them there first. -->
  <rect width="960" height="230" fill="#ffffff"/>

  <line x1="60" y1="{AXIS_Y}" x2="888" y2="{AXIS_Y}" stroke="{FOG}"
        stroke-width="2"/>
  <path d="M 888 {AXIS_Y-6} L 902 {AXIS_Y} L 888 {AXIS_Y+6} Z" fill="{FOG}"/>
  <text x="902" y="{AXIS_Y+24}" text-anchor="end" font-family="{F}"
        font-size="13" fill="{MUTED}">time</text>

  <circle cx="{P1}" cy="{AXIS_Y}" r="9" fill="{YES}"/>
  <text x="{P1}" y="{AXIS_Y-42}" text-anchor="middle" font-family="{F}"
        font-size="15" font-weight="bold" fill="{INK}">recovery point 1</text>
  <text x="{P1}" y="{AXIS_Y-20}" text-anchor="middle" font-family="{F}"
        font-size="14" fill="{MUTED}">drilled, read, attested clean</text>

  <circle cx="{P2}" cy="{AXIS_Y}" r="9" fill="#ffffff" stroke="{INK}"
          stroke-width="2"/>
  <text x="{P2}" y="{AXIS_Y-42}" text-anchor="middle" font-family="{F}"
        font-size="15" font-weight="bold" fill="{INK}">recovery point 2</text>
  <text x="{P2}" y="{AXIS_Y-20}" text-anchor="middle" font-family="{F}"
        font-size="14" fill="{MUTED}">your backup, a minute ago</text>

  <path d="M {P1-70} 128 L {P1-70} 140 L {P1+70} 140 L {P1+70} 128"
        fill="none" stroke="{YES}" stroke-width="1.5"/>
  <text x="{P1}" y="162" text-anchor="middle" font-family="{F}"
        font-size="14" fill="{YES}">the attestation covers this point</text>
  <text x="{P1}" y="182" text-anchor="middle" font-family="{F}"
        font-size="14" fill="{YES}">and nothing after it</text>

  <text x="{P2}" y="162" text-anchor="middle" font-family="{F}"
        font-size="14" fill="{MUTED}">nothing has looked at it</text>
  <text x="{P2}" y="184" text-anchor="middle" font-family="{F}"
        font-size="14" fill="{MUTED}">so the gate says
    <tspan font-weight="bold" fill="{NO}">HOLD</tspan>, and it is right</text>
</svg>
'''

out = REPO / "images" / "proof-timeline.svg"
out.write_text(svg)
print(f"wrote {out} ({out.stat().st_size} bytes)")
