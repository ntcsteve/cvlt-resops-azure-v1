"""Workshop IR -> one self-contained HTML page.

One renderer per block type; the shell (topbar, sidebar, pager) knows page
titles and counts, never content. All style lives in assets/*.css, all
behavior in assets/app.js; this module only produces markup.

Two build modes from one markdown:
  solo  every chapter renders in full (the self-paced product)
  room  chapters tagged SOLO are not rendered at all; each one's ✦
        checkpoint rides on the next rendered page as what the
        participant arrives holding. Chapters are numbered per build.

The step rail: within a page, each command block opens a numbered step and
everything until the next command belongs to it. Derived purely from the
order authored in the markdown.
"""

import html
import re

# ---------------------------------------------------------------- inline text

def esc(s):
    return html.escape(s, quote=False)


def inline(s):
    s = esc(s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<span class="doclink">\1</span>', s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
    return s


VERDICTS_YES = ("PROMOTE", "VALIDATED")
VERDICTS_NO = ("HOLD", "THREATS DETECTED")


def verdicts(escaped):
    """Tint verdict words independently of the box they sit in: a ✓ box may
    legitimately expect a HOLD, and the word must read as the gate's verdict
    even inside a green "you are on track" box."""
    for word in VERDICTS_YES:
        escaped = re.sub(rf"\b{word}\b",
                         f'<span class="v-yes">{word}</span>', escaped)
    for word in VERDICTS_NO:
        escaped = re.sub(rf"\b{word}\b",
                         f'<span class="v-no">{word}</span>', escaped)
    return escaped


def sentence(label):
    """Authored labels are uppercase for the markdown's ASCII voice; the
    page speaks sentence case. Presentation only, the words are untouched."""
    return label[:1].upper() + label[1:].lower() if label else label


# ---------------------------------------------------------------- blocks

DIAG_CLASS = {"✓": "yes", "✗": "no", "⏱": "clock"}


def render_nodes(nodes, images, mode='solo', icons=None, attest=None):
    out = []
    for node in nodes:
        kind = node[0]
        if kind == "p":
            out.append(f"<p>{inline(node[1])}</p>")
        elif kind == "quote":
            out.append(f"<blockquote>{inline(node[1])}</blockquote>")
        elif kind in ("h2", "h3"):
            out.append(f"<{kind}>{inline(node[1])}</{kind}>")
        elif kind == "h2s":                      # a chapter's ### section
            out.append(f'<h2 class="section">{inline(node[1])}</h2>')
        elif kind == "cmd":
            out.append(render_cmd(node[1]))
        elif kind == "diag":
            out.append(render_diag(node[1]))
        elif kind == "aside":
            out.append(render_aside(node, mode))
        elif kind == "reveal":
            out.append(render_reveal(node[1], node[2]))
        elif kind == "mark":
            out.append(render_titled(node, "mark", "mark-title"))
        elif kind == "dolearn":
            out.append(render_dolearn(node[1]))
        elif kind == "deflist":
            out.append(render_deflist(node[1], icons, len(node) > 2 and node[2]))
        elif kind == "attestation":
            out.append(render_attestation(attest))
        elif kind == "statement":
            out.append(
                '<div class="statement">'
                + "".join(f"<p>{inline(l)}</p>" for l in node[1])
                + "</div>")
        elif kind == "panel":
            out.append(f'<pre class="panel">{esc(node[1])}</pre>')
        elif kind == "fig":
            out.append(render_fig(node[1], node[2], images))
        else:
            raise SystemExit(f"unrendered node kind {kind!r}")
    return "\n".join(out)


def render_attestation(facts):
    """The one claim on this page that a platform-published workshop cannot
    make. AWS Workshop Studio ships no dates at all; Google Codelabs stamps a
    fresh `last-updated` on a page teaching Node 12 and gcr.io. This says
    which half of the guide is machine-checked and which half is transcribed.

    PURE, like everything else here: build.py reads the walk record and the
    offline step list and hands the numbers in, so this module still only
    produces markup."""
    facts = facts or {}
    walked = ""
    if facts.get("walked_at"):
        walked = (f", last walked {facts['walked_at']} at "
                  f"{facts['walked_commit']}")
    rows = [
        ("OFFLINE", f"{facts.get('verified', 0)} of the {facts.get('total', 0)} "
                    "commands in this guide need no cloud account, and every "
                    "one of those is re-run and "
                    "compared against the box you see by the same suite that "
                    "gates this file. If the tool stopped printing what a box "
                    "promises, this page would not have been built."),
        ("LIVE", f"{facts.get('live', 0)} of the {facts.get('total', 0)} run "
                 "against a real Azure subscription and a "
                 "real Commvault tenant. Their boxes are a transcript of a "
                 f"full rehearsal, not a reconstruction{walked}. A guard fails "
                 "the build when the code behind a quoted line changes and "
                 "the walk has not caught up."),
        ("IF A BOX IS WRONG", "Say so. Every box here is meant to reproduce, "
                              "and one that does not is a defect in this "
                              "guide rather than a mistake you made."),
    ]
    out = ['<div class="attest">']
    for label, text in rows:
        out.append(f'<div class="attest-row"><span>{esc(label)}</span>'
                   f"<p>{inline(text)}</p></div>")
    out.append("</div>")
    return "".join(out)


def render_cmd(code):
    return ('<div class="cmd" data-copy>'
            '<div class="cmd-head"><span>terminal</span>'
            '<button class="copy" type="button">copy</button></div>'
            f"<pre><code>{esc(code)}</code></pre></div>")


def render_diag(rows):
    """A diagnostic row has two halves and they are not the same kind of text.

    The label line is DESCRIPTION: the author's sentence about what the
    participant is looking at. It is prose, so it flows to the full content
    width and rewraps with the window.

    The indented continuation is QUOTED OUTPUT: line breaks carry meaning
    (a ladder bar, an aggregate line), so it stays preformatted.

    Rendering both as one <pre> is why expected-output boxes used to wrap at
    the ~46 columns they happened to be authored at, inside a container twice
    that wide, breaking sentences mid-clause for no reason. ✗ and ⏱ rows are
    guidance throughout and have no quoted half."""
    parts = ['<aside class="diag" role="note">']
    for row in rows:
        cls = DIAG_CLASS[row["glyph"]]
        chunks = []
        if row["text"]:
            chunks.append(
                f'<p class="diag-text">{verdicts(esc(row["text"]))}</p>')
        if row["cont"]:
            if row["glyph"] == "✓":
                quoted = "\n".join(row["cont"])
                chunks.append(f"<pre>{verdicts(esc(quoted))}</pre>")
            else:
                flowed = " ".join(l.strip() for l in row["cont"] if l.strip())
                chunks.append(
                    f'<p class="diag-text">{verdicts(esc(flowed))}</p>')
        content = "".join(chunks)
        parts.append(
            f'<div class="diag-row diag-{cls}">'
            f'<p class="diag-label"><span class="diag-mark">{row["glyph"]}'
            f"</span>{esc(sentence(row['label']))}</p>{content}</div>")
    parts.append("</aside>")
    return "\n".join(parts)


def render_parts(parts):
    out = []
    for kind, text in parts:
        if kind == "prose":
            out.append(f"<p>{inline(text)}</p>")
        else:
            out.append(f"<pre>{esc(text)}</pre>")
    return "\n".join(out)


def render_titled(node, cls, title_cls):
    _, title, parts = node
    marker = "? " if cls == "aside" else "✦ "
    tag = "aside" if cls == "aside" else "div"
    role = ' role="note"' if cls == "aside" else ""
    return (f'<{tag} class="{cls}"{role}><p class="{title_cls}">{marker}'
            f"{esc(sentence(title))}</p>{render_parts(parts)}</{tag}>")


def render_aside(node, mode):
    """An aside explains WHY. In a SOLO build the page is the only teacher, so
    it is open. In a ROOM the facilitator is the teacher, and several of these
    are their lines: the reveal in Break is the moment the day turns on. A page
    that prints it beside the command hands the punchline to anyone reading
    ahead, and competes with the human for the same 15 minutes.

    So the room build collapses them. Same words, same file, one click away,
    and the take-home reading is not lost: participants who want the full text
    open it, or read the solo build afterwards."""
    if mode != "room":
        return render_titled(node, "aside", "aside-title")
    _, title, parts = node
    return (f'<details class="aside aside-fold"><summary>? '
            f"{esc(sentence(title))}</summary><div>{render_parts(parts)}"
            "</div></details>")


def render_reveal(title, parts):
    return (f'<details class="reveal"><summary>{esc(sentence(title))}'
            f"</summary><div>{render_parts(parts)}</div></details>")


def render_dolearn(rows):
    cells = "".join(
        f'<div class="dolearn-row"><span>{esc(r["label"])}</span>'
        f"<p>{inline(r['text'])}</p></div>" for r in rows)
    return f'<div class="dolearn">{cells}</div>'


def render_deflist(rows, icons=None, card=False):
    """A ```list fence: label in a mono column, text as PROSE that flows to
    the full content width and rewraps with the window.

    This is the same distinction the ✓ box makes. A plain fence is
    preformatted because a diagram's alignment is its meaning; a definition
    list is a label beside a sentence, and a sentence that breaks where the
    author's editor happened to wrap is just a narrower page for no reason."""
    icons = icons or {}
    cells = []
    any_icon = any(row.get("icon") for row in rows)
    for row in rows:
        body = "".join(f"<p>{inline(par)}</p>" for par in row["paras"])
        joined = " ".join(row["paras"])
        vclass = ""
        if any(w in joined for w in VERDICTS_YES):
            vclass = " dl-yes"
        elif any(w in joined for w in VERDICTS_NO):
            vclass = " dl-no"
        mark = ""
        if row.get("icon"):
            mark = (f'<img class="dl-icon" src="{icons[row["icon"]]}" alt="">')
        elif any_icon:
            mark = '<span class="dl-icon"></span>'   # keep the column aligned
        cells.append(f'<div class="dl-row">{mark}'
                     f'<span class="dl-key{vclass}">'
                     f'{esc(row["label"])}</span><div class="dl-val">'
                     f"{body}</div></div>")
    cls = "deflist deflist-iconed" if any_icon else "deflist"
    if card:
        cls += " deflist-card"
    return f'<div class="{cls}">{"".join(cells)}</div>'


def render_fig(caption, path, images):
    uri = images[path]
    cap = f"<figcaption>{inline(caption)}</figcaption>" if caption else ""
    return (f'<figure><img src="{uri}" alt="{html.escape(caption, quote=True)}">'
            f"{cap}</figure>")


# ---------------------------------------------------------------- steps

def render_body(nodes, images, mode='solo', icons=None, attest=None):
    """Section-aware: a ### heading or chapter-level furniture (DO/LEARN,
    ✦ checkpoint, ?! reveal) closes the step rail; step numbering runs
    continuously across a chapter's sections."""
    parts = []
    counter = 0
    rail_open = False
    step = None

    def flush_step():
        nonlocal step
        if step is not None:
            parts.append(
                f'<div class="step"><span class="step-num">{counter}</span>'
                f'<div class="step-body">{render_nodes(step, images, mode, icons, attest)}'
                "</div></div>")
            step = None

    def close_rail():
        nonlocal rail_open
        flush_step()
        if rail_open:
            parts.append("</div>")
            rail_open = False

    for node in nodes:
        kind = node[0]
        if kind == "cmd":
            flush_step()
            if not rail_open:
                parts.append('<div class="steps">')
                rail_open = True
            counter += 1
            step = [node]
        elif kind in ("h2", "h2s", "h3", "dolearn", "mark", "reveal"):
            close_rail()
            parts.append(render_nodes([node], images, mode, icons, attest))
        elif step is not None:
            step.append(node)
        else:
            parts.append(render_nodes([node], images, mode, icons, attest))
    close_rail()
    return "\n".join(parts)


def inherited_band(chapters, images):
    """A ROOM build does not render SOLO chapters, because a room does not do
    them: the facilitator provisions, drills and retires the lab in prep.

    Emitting them as their own pages produced a sidebar where a fifth of the
    entries said "there is nothing here for you". Instead each omitted
    chapter's ✦ checkpoint rides on top of the next page that IS rendered, as
    a statement of what the participant arrives holding. Nothing is lost;
    tests/test_participant_guide.py pins that every ✦ in the solo build also
    reaches the room build."""
    marks = [n for ch in chapters for n in ch["body"] if n[0] == "mark"]
    if not marks:
        return ""
    return ('<div class="inherited">'
            '<p class="inherited-title">You arrive with</p>'
            + render_nodes(marks, images) + "</div>")


# ---------------------------------------------------------------- pages

def promote_sections(nodes):
    """A page whose title came from a `## ` heading has that heading as its
    h1, so the `### ` sections beneath it are the page's SECOND level and
    have to render as <h2>. Emitting <h3> skipped a level and gave a screen
    reader a broken outline on every chapter, on Setup and on the closing
    page at once.

    The test is simply whether the page already has an h2 of its own: the
    Overview does, because its `## ` sections stay in the body, so this is a
    no-op there. Authoring never changes; `## ` remains reserved for page
    boundaries in the dialect."""
    if any(n[0] == "h2" for n in nodes):
        return list(nodes)
    return [("h2s", n[1]) if n[0] == "h3" else n for n in nodes]


def build_pages(ws, images, mode, icons=None, attest=None):
    """The ordered page list: Overview, Setup, the chapters, close."""
    overview = [n for n in ws["overview"] if n[0] != "hero"]
    pages = [{
        "route": "#/overview", "pid": "page-overview", "title": "Overview",
        "crumb": None, "kicker": None, "meta": None, "icon": None,
        "hero": next((n[1] for n in ws["overview"] if n[0] == "hero"), None),
        "body": render_body(promote_sections(overview), images, mode, icons, attest),
    }]
    if ws["setup"]:
        pages.append({
            "route": "#/setup", "pid": "page-setup", "title": "Setup",
            "crumb": None, "kicker": None, "meta": None, "icon": None,
            "body": render_body(promote_sections(ws["setup"]), images, mode, icons, attest),
        })
    # Chapters are numbered per BUILD, not per markdown: a room build omits the
    # SOLO chapters, so numbering it 1..N keeps its sidebar gapless. Solo skips
    # nothing, so there `shown` always equals the authored number.
    shown = 0
    inherited = []
    for ch in ws["chapters"]:
        if mode == "room" and ch["solo"]:
            inherited.append(ch)
            continue
        shown += 1
        band = inherited_band(inherited, images)
        inherited = []
        body_nodes = promote_sections(ch["body"])
        pages.append({
            "route": f"#/{shown}", "pid": f"page-{shown}",
            "title": f"{shown}. {ch['name']}",
            # The KICKER already says CHAPTER 3. Printing "3." again in a 48px
            # h1 says it twice, which was invisible at 40px and is not now.
            # `title` keeps the number because the browser tab, the sidebar
            # and the breadcrumb all need it to sort and locate.
            "heading": ch["name"],
            "crumb": f"Chapter {shown}",
            "kicker": f"CHAPTER {shown}", "icon": ch.get("icon"),
            "body": band + render_body(body_nodes, images, mode, icons, attest),
        })
    close_nodes = list(ws["close"])
    close_title = "Close"
    if close_nodes and close_nodes[0][0] == "h2":
        close_title = close_nodes[0][1]     # the first h2 IS the page title
        close_nodes = close_nodes[1:]
    pages.append({
        "route": "#/close", "pid": "page-close", "title": close_title,
        "crumb": None, "kicker": None, "meta": None, "icon": None,
        "body": inherited_band(inherited, images)
                + render_body(promote_sections(close_nodes), images, mode, icons, attest),
    })
    return pages


def render_hero_card(lines):
    """The masthead's terminal transcript: the workshop's whole argument in
    eight lines, above the fold. No AWS or Google workshop opens by showing
    you the punchline as evidence, and it is the most distinctive thing we
    have -- it used to be on page ten.

    A `$` opens a command; everything else is output, so the verdict words
    get the same tint they carry everywhere else on the page."""
    out = []
    for line in lines:
        if not line.strip():
            out.append('<span class="hero-gap"></span>')
        elif line.lstrip().startswith("$"):
            out.append('<span class="hero-cmd"><i>$</i>'
                       + esc(line.lstrip()[1:].strip()) + "</span>")
        else:
            out.append('<span class="hero-out">' + verdicts(esc(line)) + "</span>")
    return f'<div class="hero-card" aria-hidden="true">{"".join(out)}</div>'


def render_landing_head(ws, hero=None):
    """The codename chip was removed on 2026-08-19. The codename still does
    its real work inside the ✓ expected-output boxes, where a participant
    compares their own resource names against the page; a chip restating it
    at the top was a label with nothing to label."""
    stand = (f'<p class="standfirst">{inline(ws["standfirst"])}</p>'
             if ws["standfirst"] else "")
    meta = f'<p class="mast-meta">{inline(ws["meta"])}</p>' if ws["meta"] else ""
    card = render_hero_card(hero) if hero else ""
    return ('<div class="mast"><div class="mast-text">'
            '<header class="page-head"><h1>'
            f"{esc(ws['title'])}</h1></header>{stand}{meta}"
            f"</div>{card}</div>")


def render_page_sections(ws, pages):
    out = []
    for k, page in enumerate(pages):
        crumb = ""
        if page["crumb"]:
            crumb = ('<nav class="crumb" aria-label="Breadcrumb">'
                     f'<a href="#/overview">{esc(ws["title"])}</a>'
                     '<span class="crumb-sep">›</span>'
                     f"<b>{esc(page['title'])}</b></nav>")
        if page["pid"] == "page-overview":
            head = render_landing_head(ws, page.get("hero"))
        else:
            kicker = (f'<p class="kicker">{esc(page["kicker"])}</p>'
                      if page["kicker"] else "")
            head = (f'{kicker}<header class="page-head">'
                    f'<h1>{esc(page.get("heading") or page["title"])}'
                    f'</h1></header>')
        pager = render_pager(pages, k)
        out.append(
            f'<section class="page" id="{page["pid"]}" '
            f'data-route="{page["route"]}" data-title="{esc(page["title"])}">'
            f"{crumb}{head}{page['body']}{pager}</section>")
    return "\n".join(out)


def render_pager(pages, k):
    parts = ['<nav class="pager" aria-label="Pages">']
    if k > 0:
        p = pages[k - 1]
        parts.append(f'<a class="pager-prev" href="{p["route"]}">'
                     f'← {esc(p["title"])}</a>')
    if k < len(pages) - 1:
        p = pages[k + 1]
        parts.append(f'<a class="pager-next" href="{p["route"]}">'
                     f'{esc(p["title"])} →</a>')
    parts.append("</nav>")
    return "".join(parts)


# ---------------------------------------------------------------- shell

def render_sidebar(pages):
    """The sidebar is the page list, nothing else: Overview, Setup, the
    numbered chapters, the closing page. No ticks, no times, no badges.

    Chapters carry an official Commvault icon, authored as `@name` on the
    heading. It is navigation rather than decoration -- Mintlify and GitBook
    both do this -- and pages without one keep the same indent so the column
    stays straight."""
    rows = []
    for p in pages:
        m = re.match(r"^(\d+)\. (.*)$", p["title"])
        num = (f'<span class="nav-num">{m.group(1)}.</span>' if m else "")
        name = m.group(2) if m else p["title"]
        rows.append(
            f'<a class="nav-row" href="{p["route"]}" '
            f'data-route="{p["route"]}">{num}'
            f'<span class="nav-name">{esc(name)}</span></a>')
    return ('<aside id="sidebar"><nav aria-label="Workshop contents">'
            + "".join(rows) + "</nav></aside>")


def render_topbar(ws, brand):
    """brand: {"mark": data_uri, "wordmark": data_uri} from assets/,
    inlined by the build so the file stays self-contained."""
    return (
        '<header id="topbar">'
        f'<a class="brand" href="#/overview">'
        f'<img class="brand-logo" src="{brand["mark"]}" alt="">'
        f'<span class="brand-name">{esc(ws["title"])}</span></a>'
        '<span id="topbar-here"></span>'
        f'<img class="topbar-wordmark" src="{brand["wordmark"]}" '
        'alt="Commvault">'
        "</header>")


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}</title>
<link rel="icon" href="{{FAVICON}}">
<style>
{{CSS}}
</style>
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
{{TOPBAR}}
<div class="shell">
{{SIDEBAR}}
<main id="main" tabindex="-1">
{{PAGES}}
</main>
</div>
<script>
{{JS}}
</script>
</body>
</html>
"""


def render_document(ws, css, js, images, brand, mode, icons=None, attest=None):
    pages = build_pages(ws, images, mode, icons, attest)
    return (TEMPLATE
            .replace("{{TITLE}}", esc(ws["title"]))
            .replace("{{FAVICON}}", brand["favicon"])
            .replace("{{CSS}}", css)
            .replace("{{TOPBAR}}", render_topbar(ws, brand))
            .replace("{{SIDEBAR}}", render_sidebar(pages))
            .replace("{{PAGES}}", render_page_sections(ws, pages))
            .replace("{{JS}}", js))
