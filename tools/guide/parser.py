"""WORKSHOP-2H.md dialect -> typed IR.

WORKSHOP-2H.md is the ONLY place content is authored. This parser accepts
exactly the constructs below and raises SystemExit on anything else: a loose
document is a bug in the markdown, never a reason to hand-edit HTML.

The dialect:
  # TITLE                       first h1 = workshop title
  # ACT N · NAME                act header, then a **time · mode** line
  ## Beat N · Name · Nm · MODE  beat header (time and mode optional)
  ## / ### other headings       plain sections (setup before act I, close after)
  > quote                       blockquote
  ---                           separator (ignored)
  ![caption](images/x.png)      figure, inlined as a data URI at build time
  ```bash fences                participant commands
  ``` fences starting ✓/✗/⏱     diagnostic rows (expected / if-not / timing)
  ``` fences starting ?         quiet aside
  ``` other fences              preformatted ASCII panel
  prose paragraphs              inline **bold**, *italic*, `code`, [links](x)

IR shape (plain dicts and tuples, no classes to maintain):
  workshop = {
    "title": str,
    "standfirst": str,        # the intro blockquote, rendered in the masthead
    "meta": str,              # the **Level** ... line, rendered in the masthead
    "setup": [node, ...],     # start-page body after masthead extraction
    "acts":  [{"num", "name", "meta", "beats": [
                 {"num", "name", "time", "mode", "body": [node, ...]}],
               "intro": [node, ...]}],
    "close": [node, ...],
  }
"""

import re

GLYPHS = "✓✗⏱"


def parse(text):
    """Markdown dialect -> flat node list. Raises on anything unrecognized."""
    nodes = []
    lines = text.split("\n")
    i, n = 0, len(lines)
    para = []

    def flush():
        if para:
            nodes.append(("p", " ".join(para)))
            para.clear()

    while i < n:
        stripped = lines[i].strip()

        if stripped.startswith("```"):
            flush()
            fence_line = i + 1          # 1-based, for error messages
            lang = stripped[3:].strip()
            body = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                body.append(lines[i])
                i += 1
            if i >= n:
                raise SystemExit(f"line {fence_line}: fence is never closed")
            i += 1
            nodes.append(classify_fence(lang, body, fence_line))
            continue

        if stripped == "---":
            flush()
            i += 1
            continue

        if stripped.startswith(">"):
            flush()
            quote = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            nodes.append(("quote", " ".join(q for q in quote if q)))
            continue

        m = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", stripped)
        if m:
            flush()
            nodes.append(("fig", m.group(1), m.group(2)))
            i += 1
            continue

        m = re.match(r"^# ACT ([IV]+) · (.+)$", stripped)
        if m:
            flush()
            nodes.append(("act", m.group(1), m.group(2).strip()))
            i += 1
            continue

        m = re.match(r"^# (.+)$", stripped)
        if m:
            flush()
            nodes.append(("title", m.group(1).strip()))
            i += 1
            continue

        m = re.match(r"^## Beat (\d) · (.+)$", stripped)
        if m:
            flush()
            parts = [p.strip() for p in m.group(2).split("·")]
            name = parts[0]
            time = next((p for p in parts[1:] if re.match(r"^\d+ ?min$", p)), "")
            mode = next((p for p in parts[1:] if p in ("OFFLINE", "LIVE")), "")
            nodes.append(("beat", int(m.group(1)), name, time, mode))
            i += 1
            continue

        m = re.match(r"^(#{2,3}) (.+)$", stripped)
        if m:
            flush()
            nodes.append(("h%d" % len(m.group(1)), m.group(2).strip()))
            i += 1
            continue

        if stripped == "":
            flush()
            i += 1
            continue

        para.append(stripped)
        i += 1

    flush()
    return nodes


GLYPH_LOOKALIKES = "✅❎❌✔✖☑⏰⏲"
DIAG_WORDS = re.compile(r"^(YOU SHOULD SEE|IF NOT|HOW LONG)\b")


def classify_fence(lang, body, fence_line):
    if lang == "bash":
        return ("cmd", "\n".join(body).strip())
    if lang != "":
        raise SystemExit(
            f"line {fence_line}: unknown fence language {lang!r}; the "
            "dialect knows ```bash and plain fences only")
    first = next((l.strip() for l in body if l.strip()), "")
    if first and first[0] in GLYPHS:
        return ("diag", diag_rows(body, fence_line + 1))
    if first.startswith("?"):
        return aside(body)
    check_not_a_mistyped_diag(body, fence_line + 1)
    return ("panel", dedent(body))


def check_not_a_mistyped_diag(body, body_start):
    """A fence that smells like a diagnostic block but is not one must be
    a loud error, never a silently-rendered panel. Unknown is never a pass."""
    for idx, line in enumerate(body):
        s = line.strip()
        if not s:
            continue
        if s[0] in GLYPH_LOOKALIKES:
            raise SystemExit(
                f"line {body_start + idx}: {s[0]!r} looks like a diagnostic "
                "glyph but the dialect uses exactly ✓ ✗ ⏱; without them "
                "this fence would render as a plain panel")
        if DIAG_WORDS.match(s):
            raise SystemExit(
                f"line {body_start + idx}: this fence reads like a "
                f"diagnostic block ({s.split('  ')[0]!r}) but does not "
                "start with ✓ ✗ or ⏱")


def diag_rows(body, body_start):
    """Split a ✓/✗/⏱ fence into rows; unglyphed lines continue the row above."""
    rows = []
    for idx, line in enumerate(body):
        s = line.strip()
        if s and s[0] in GLYPHS:
            rest = s[1:].strip()
            m = re.match(r"^([A-Z][A-Z ',-]*?)(?:\s{2,}(.*))?$", rest)
            if not m:
                raise SystemExit(
                    f"line {body_start + idx}: diagnostic row {s!r} has no "
                    "label; the rule is an UPPERCASE label, then two or "
                    "more spaces, then the text")
            rows.append({"glyph": s[0], "label": m.group(1).strip(),
                         "text": (m.group(2) or "").strip(), "cont": []})
        elif rows:
            rows[-1]["cont"].append(line)
        elif s:
            raise SystemExit(
                f"line {body_start + idx}: diagnostic fence starts with "
                f"{s!r} instead of a ✓ ✗ or ⏱ row")
    for row in rows:
        row["cont"] = dedent(row["cont"]).split("\n") if any(
            l.strip() for l in row["cont"]) else []
    return rows


def aside(body):
    """A '?' fence: title line, then prose paragraphs and indented pre chunks."""
    first = next(l for l in body if l.strip())
    title = first.strip()[1:].strip()
    rest = body[body.index(first) + 1:]
    rest = dedent(rest).split("\n") if any(l.strip() for l in rest) else []
    chunks, current, kind = [], [], None
    for line in rest + [""]:
        this = None if line.strip() == "" else (
            "pre" if line.startswith("   ") else "prose")
        if this != kind and current:
            chunks.append((kind, current))
            current = []
        kind = this
        if this:
            current.append(line)
    parts = []
    for k, block in chunks:
        if k == "prose":
            parts.append(("prose", " ".join(l.strip() for l in block)))
        else:
            parts.append(("pre", dedent(block)))
    return ("aside", title, parts)


def dedent(block):
    keep = [l for l in block if l.strip()]
    if not keep:
        return ""
    cut = min(len(l) - len(l.lstrip()) for l in keep)
    out = [l[cut:] if l.strip() else "" for l in block]
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out)


def group(nodes):
    """Flat nodes -> the workshop IR described in the module docstring."""
    title = ""
    setup, acts, close = [], [], []
    beat = None
    act = None
    seen_act = False

    for node in nodes:
        kind = node[0]
        if kind == "title":
            title = node[1]
            continue
        if kind == "act":
            act = {"num": node[1], "name": node[2], "meta": "",
                   "beats": [], "intro": []}
            acts.append(act)
            beat = None
            seen_act = True
            continue
        if kind == "beat":
            beat = {"num": node[1], "name": node[2], "time": node[3],
                    "mode": node[4], "body": []}
            act["beats"].append(beat)
            continue
        if seen_act and kind == "h2":
            beat = None
            act = None
            close.append(node)
            continue
        if act is not None and not act["meta"] and kind == "p" \
                and beat is None and re.match(r"^\*\*[^*]+\*\*$", node[1]):
            act["meta"] = node[1].strip("*")
            continue
        if beat is not None:
            beat["body"].append(node)
        elif act is not None:
            act["intro"].append(node)
        elif seen_act:
            close.append(node)
        else:
            setup.append(node)

    standfirst, meta, setup = _split_masthead(setup)
    return {"title": title, "standfirst": standfirst, "meta": meta,
            "setup": setup, "acts": acts, "close": close}


def _split_masthead(setup):
    """Pull the intro blockquote and the **Level** line into the masthead.

    Presentation only: both stay authored in WORKSHOP-2H.md; they are simply
    rendered as the landing header instead of as body copy.
    """
    standfirst, meta = "", ""
    rest = []
    for node in setup:
        if not standfirst and node[0] == "quote":
            standfirst = node[1]
        elif not meta and node[0] == "p" and node[1].startswith("**Level**"):
            meta = node[1]
        else:
            rest.append(node)
    return standfirst, meta, rest


def check(workshop):
    """Structural invariants. Shape is content, so the check validates
    internal consistency, never a fixed count: beats numbered 1..N in
    order across the acts, at least one act, no empty act. A workshop's
    specific shape is pinned where pins belong: in its own tests."""
    if not workshop["title"]:
        raise SystemExit("no # TITLE found: fix the markdown")
    if not workshop["acts"]:
        raise SystemExit("no # ACT headers found: fix the markdown")
    expected = 1
    for act in workshop["acts"]:
        if not act["beats"]:
            raise SystemExit(f"ACT {act['num']} has no beats: fix the markdown")
        for beat in act["beats"]:
            if beat["num"] != expected:
                raise SystemExit(
                    f"beat numbering breaks at '{beat['name']}': found "
                    f"Beat {beat['num']}, expected Beat {expected}. "
                    "Beats run 1..N in order: fix the markdown")
            expected += 1
