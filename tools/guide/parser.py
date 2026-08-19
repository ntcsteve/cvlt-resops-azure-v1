"""WORKSHOP-2H.md dialect -> typed IR.

The markdown is the ONLY place content is authored. This parser accepts
exactly the constructs below and raises SystemExit with a line number on
anything else: a loose document is a bug in the markdown, never a reason
to hand-edit HTML.

The dialect:
  # TITLE                       first h1 = workshop title
  ## Chapter N · Name · @icon · SOLO
                                one page per chapter. @icon puts an official
                                Commvault icon in the sidebar. SOLO is a tag
                                and it is optional: a SOLO chapter is
                                omitted from a room-mode build, its ✦
                                checkpoint carried onto the next page.
  ## / ### other headings       start-page sections before chapter 1,
                                closing-page sections after the last
  > quote                       blockquote
  ---                           separator (ignored)
  ![caption](images/x.png)      figure, inlined as a data URI at build
  ```bash fences                participant commands
  ``` starting ✓/✗/⏱            diagnostic rows (expected / if-not / timing)
  ```hero fences                a terminal transcript for the masthead. One
                                per workshop, authored in the front matter,
                                rendered beside the title rather than in the
                                body. `$` opens a command line.
  ```statement fences           display type. For the one or two lines the
                                workshop exists to make somebody repeat.
                                Inline markup is processed, so **bold**
                                carries the punch line.
  ```list fences                a definition list: `label  text` rows,
                                label in a column, text FLOWING full width.
                                An optional `@icon-name ` prefix attaches an
                                official Commvault icon to the row
  ``` starting DO               the DO/LEARN orientation strip
  ``` starting ?!               a collapsed reveal (answers), title first
  ``` starting ?                a quiet aside, title first
  ``` starting ✦                a checkpoint card, title first
  ``` other fences              preformatted ASCII panel
  prose paragraphs              inline **bold**, *italic*, `code`, [links](x)

IR shape (plain dicts, no classes to maintain):
  workshop = {
    "title": str, "standfirst": str, "meta": str,
    "setup": [node, ...],
    "chapters": [{"num", "name", "solo", "body": [...]}],
    "close": [node, ...],
  }
"""

import re

GLYPHS = "✓✗⏱"
GLYPH_LOOKALIKES = "✅❎❌✔✖☑⏰⏲"
DIAG_WORDS = re.compile(r"^(YOU SHOULD SEE|IF NOT|HOW LONG)\b")


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

        m = re.match(r"^# (.+)$", stripped)
        if m and not stripped.startswith("## "):
            flush()
            nodes.append(("title", m.group(1).strip()))
            i += 1
            continue

        m = re.match(r"^## Chapter (\d+) · (.+)$", stripped)
        if m:
            flush()
            parts = [p.strip() for p in m.group(2).split("·")]
            name = parts[0]
            # SOLO is the ONLY tag a chapter heading carries. Per-chapter time
            # and mode badges were removed on 2026-08-19: the page no longer
            # shows them, so the markdown no longer holds them. A leftover
            # `~15 min` or `LIVE` is a hard error rather than a silent no-op,
            # because data nothing displays is data nobody maintains.
            icon = next((p[1:] for p in parts[1:] if p.startswith("@")), None)
            unknown = [p for p in parts[1:]
                       if p != "SOLO" and not p.startswith("@")]
            if unknown:
                raise SystemExit(
                    f"line {i + 1}: chapter heading carries {unknown!r}; a "
                    "chapter takes SOLO and an @icon-name, nothing else. "
                    "Per-chapter time and mode are not rendered, so they are "
                    "not authored. See tools/guide/DIALECT.md.")
            nodes.append(("chapter", int(m.group(1)), name,
                          any(p == "SOLO" for p in parts[1:]), icon))
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


def classify_fence(lang, body, fence_line):
    if lang == "bash":
        return ("cmd", "\n".join(body).strip())
    if lang == "hero":
        return ("hero", [l.rstrip() for l in body])
    if lang == "statement":
        return ("statement", [l.strip() for l in body if l.strip()])
    if lang in ("list", "list card"):
        return ("deflist", list_rows(body, fence_line + 1), lang == "list card")
    if lang == "attestation":
        # The AUTHOR chooses where this goes; the BUILD decides what it says,
        # from tests/workshop_walk.json and the offline step list. A body is
        # refused outright, because a hand-written provenance claim is the
        # exact failure this block exists to avoid -- Google Codelabs stamps
        # "last updated 2026-03-20" on a page teaching Node 12.
        if any(l.strip() for l in body):
            raise SystemExit(
                f"line {fence_line}: ```attestation takes NO body. What it "
                "says is generated from the walk record; writing it by hand "
                "is how a freshness stamp becomes a lie.")
        return ("attestation",)
    if lang != "":
        raise SystemExit(
            f"line {fence_line}: unknown fence language {lang!r}; the "
            "dialect knows ```bash, ```list, ```list card, ```statement, "
            "```hero, ```attestation and plain fences only")
    first = next((l.strip() for l in body if l.strip()), "")
    if first and first[0] in GLYPHS:
        return ("diag", diag_rows(body, fence_line + 1))
    if first.startswith("?!"):
        return labeled(body, "reveal", 2)
    if first.startswith("?"):
        return labeled(body, "aside", 1)
    if first.startswith("✦"):
        return labeled(body, "mark", 1)
    if re.match(r"^DO\s{2,}", first):
        return ("dolearn", strip_rows(body, fence_line + 1))
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


def list_rows(body, body_start):
    """A ```list fence: a definition list of `label  text` rows.

    WHY THIS EXISTS. Most of this guide's list content is not a diagram, it
    is a label beside a sentence. Authored in a plain fence it rendered
    preformatted, so it broke wherever the AUTHOR happened to wrap it and
    used about half the page. Prose has to reflow; a diagram must not. The
    build cannot tell them apart safely -- a two-column table has no box
    characters either -- so the author says which, the same way ```bash
    already says a fence is a command.

    A blank line inside a row's continuation starts a new paragraph."""
    rows = []
    # Fence bodies in this dialect are indented one space by house style, so
    # "column zero" is the shallowest indent present, not literal column 0.
    kept = [l for l in body if l.strip()]
    base = min(len(l) - len(l.lstrip()) for l in kept) if kept else 0
    for idx, line in enumerate(body):
        s = line.strip()
        if not s and rows:
            rows[-1]["cont"].append("")
            continue
        if not s:
            continue
        if len(line) - len(line.lstrip()) <= base:
            # An optional @icon-name prefix attaches an official Commvault
            # icon to the row. Explicit in the markdown on purpose: an icon
            # chosen by a lookup table somewhere in the build would be a
            # second home for a decision the author is making.
            icon = None
            im = re.match(r"^@([a-z0-9-]+)\s+(.*)$", s)
            if im:
                icon, s = im.group(1), im.group(2).strip()
            m = re.match(r"^(\S.*?)\s{2,}(.*)$", s)
            if not m:
                raise SystemExit(
                    f"line {body_start + idx}: list row {s!r} has no text; "
                    "the rule is a label, then two or more spaces, then the "
                    "text. Indent a line to continue the row above.")
            rows.append({"label": m.group(1).strip(), "icon": icon,
                         "text": m.group(2).strip(), "cont": []})
        elif rows:
            rows[-1]["cont"].append(s)
        else:
            raise SystemExit(
                f"line {body_start + idx}: a ```list fence starts with an "
                f"indented line {s!r}; the first line must be a label row")
    for row in rows:
        paras, current = [], [row["text"]]
        for piece in row["cont"]:
            if piece == "":
                if current: paras.append(" ".join(current)); current = []
            else:
                current.append(piece)
        if current:
            paras.append(" ".join(current))
        row["paras"] = [x for x in paras if x]
    return rows


def strip_rows(body, body_start):
    """The DO/LEARN strip: UPPERCASE label, two+ spaces, text;
    continuation lines join the row above."""
    rows = []
    for idx, line in enumerate(body):
        s = line.strip()
        m = re.match(r"^([A-Z]+)\s{2,}(.*)$", s) if s else None
        if m:
            rows.append({"label": m.group(1), "text": m.group(2).strip()})
        elif rows and s:
            rows[-1]["text"] += " " + s
        elif s:
            raise SystemExit(
                f"line {body_start + idx}: strip row {s!r} has no "
                "UPPERCASE label")
    return rows


def labeled(body, kind, marker_len):
    """A titled fence (? aside, ?! reveal, ✦ mark): title on the first
    line after the marker, then prose paragraphs and indented pre chunks."""
    first = next(l for l in body if l.strip())
    title = first.strip()[marker_len:].strip()
    rest = body[body.index(first) + 1:]
    rest = dedent(rest).split("\n") if any(l.strip() for l in rest) else []
    chunks, current, current_kind = [], [], None
    for line in rest + [""]:
        this = None if line.strip() == "" else (
            "pre" if line.startswith("   ") else "prose")
        if this != current_kind and current:
            chunks.append((current_kind, current))
            current = []
        current_kind = this
        if this:
            current.append(line)
    parts = []
    for k, block in chunks:
        if k == "prose":
            parts.append(("prose", " ".join(l.strip() for l in block)))
        else:
            parts.append(("pre", dedent(block)))
    return (kind, title, parts)


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
    """Flat nodes -> the workshop IR described in the module docstring.

    Pages: front matter before chapter 1 becomes the Overview page, split
    into Overview + Setup at a `## Setup` heading if one exists. A bare
    `## ` heading after the chapters starts the closing page (its first
    h2 is that page's title). Inside chapters, sections use `### ` only;
    a stray `## ` there would silently start the closing page, so a
    chapter appearing after closing content is a hard error."""
    title = ""
    front, chapters, close = [], [], []
    chapter = None
    seen_chapter = False

    for node in nodes:
        kind = node[0]
        if kind == "title":
            title = node[1]
            continue
        if kind == "chapter":
            if close:
                raise SystemExit(
                    "'## Chapter' found after closing-page content began. "
                    "A bare '## ' heading inside a chapter starts the "
                    "closing page; use '### ' for sections inside chapters")
            chapter = {"num": node[1], "name": node[2], "solo": node[3],
                       "icon": node[4], "body": []}
            chapters.append(chapter)
            seen_chapter = True
            continue
        if seen_chapter and kind == "h2":
            chapter = None
            close.append(node)
            continue
        if chapter is not None:
            chapter["body"].append(node)
        elif seen_chapter:
            close.append(node)
        else:
            front.append(node)

    standfirst, meta, front = _split_masthead(front)
    overview, setup = front, []
    for k, node in enumerate(front):
        if node[0] == "h2" and node[1] == "Setup":
            overview, setup = front[:k], front[k + 1:]
            break
    return {"title": title, "standfirst": standfirst, "meta": meta,
            "overview": overview, "setup": setup,
            "chapters": chapters, "close": close}


def _split_masthead(setup):
    """Pull the intro blockquote and the **Level** line into the landing
    header. Presentation only: both stay authored in the markdown."""
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
    internal consistency, never a fixed count: chapters numbered 1..N in
    order. A workshop's specific shape is pinned in its own tests."""
    if not workshop["title"]:
        raise SystemExit("no # TITLE found: fix the markdown")
    if not workshop["chapters"]:
        raise SystemExit("no '## Chapter N ·' headings found: fix the markdown")
    for expected, chapter in enumerate(workshop["chapters"], 1):
        if chapter["num"] != expected:
            raise SystemExit(
                f"chapter numbering breaks at '{chapter['name']}': found "
                f"Chapter {chapter['num']}, expected Chapter {expected}. "
                "Chapters run 1..N in order: fix the markdown")
