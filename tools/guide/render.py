"""Workshop IR -> one self-contained HTML page.

One renderer per block type; the shell (topbar, sidebar, pager) knows page
titles and counts, never content. All style lives in assets/*.css, all
behavior in assets/app.js; this module only produces markup.

Two build modes from one markdown:
  solo  every chapter renders in full (the self-paced product)
  room  chapters tagged SOLO render as inherited stubs: one sentence plus
        that chapter's ✦ checkpoint as the summary of what participants
        arrive with. Numbering stays stable across modes.

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


def render_nodes(nodes, images):
    out = []
    for node in nodes:
        kind = node[0]
        if kind == "p":
            out.append(f"<p>{inline(node[1])}</p>")
        elif kind == "quote":
            out.append(f"<blockquote>{inline(node[1])}</blockquote>")
        elif kind in ("h2", "h3"):
            out.append(f"<{kind}>{inline(node[1])}</{kind}>")
        elif kind == "cmd":
            out.append(render_cmd(node[1]))
        elif kind == "diag":
            out.append(render_diag(node[1]))
        elif kind == "aside":
            out.append(render_titled(node, "aside", "aside-title"))
        elif kind == "reveal":
            out.append(render_reveal(node[1], node[2]))
        elif kind == "mark":
            out.append(render_titled(node, "mark", "mark-title"))
        elif kind == "dolearn":
            out.append(render_dolearn(node[1]))
        elif kind == "panel":
            out.append(f'<pre class="panel">{esc(node[1])}</pre>')
        elif kind == "fig":
            out.append(render_fig(node[1], node[2], images))
        else:
            raise SystemExit(f"unrendered node kind {kind!r}")
    return "\n".join(out)


def render_cmd(code):
    return ('<div class="cmd" data-copy>'
            '<div class="cmd-head"><span>terminal</span>'
            '<button class="copy" type="button">copy</button></div>'
            f"<pre><code>{esc(code)}</code></pre></div>")


def render_diag(rows):
    """✓ rows quote OUTPUT: line breaks are meaning, so they render
    preformatted. ✗ and ⏱ rows are GUIDANCE: prose that flows to the
    full content width."""
    parts = ['<div class="diag">']
    for row in rows:
        cls = DIAG_CLASS[row["glyph"]]
        if row["glyph"] == "✓":
            body = row["text"]
            if row["cont"]:
                body = (body + "\n" if body else "") + "\n".join(row["cont"])
            content = f"<pre>{verdicts(esc(body))}</pre>"
        else:
            joined = " ".join(
                [row["text"]] + [l.strip() for l in row["cont"] if l.strip()])
            content = f'<p class="diag-text">{verdicts(esc(joined.strip()))}</p>'
        parts.append(
            f'<div class="diag-row diag-{cls}">'
            f'<p class="diag-label"><span class="diag-mark">{row["glyph"]}'
            f"</span>{esc(sentence(row['label']))}</p>{content}</div>")
    parts.append("</div>")
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
    return (f'<div class="{cls}"><p class="{title_cls}">{marker}'
            f"{esc(sentence(title))}</p>{render_parts(parts)}</div>")


def render_reveal(title, parts):
    return (f'<details class="reveal"><summary>{esc(sentence(title))}'
            f"</summary><div>{render_parts(parts)}</div></details>")


def render_dolearn(rows):
    cells = "".join(
        f'<div class="dolearn-row"><span>{esc(r["label"])}</span>'
        f"<p>{inline(r['text'])}</p></div>" for r in rows)
    return f'<div class="dolearn">{cells}</div>'


def render_fig(caption, path, images):
    uri = images[path]
    cap = f"<figcaption>{inline(caption)}</figcaption>" if caption else ""
    return (f'<figure><img src="{uri}" alt="{html.escape(caption, quote=True)}">'
            f"{cap}</figure>")


# ---------------------------------------------------------------- steps

def render_body(nodes, images):
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
                f'<div class="step-body">{render_nodes(step, images)}'
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
        elif kind in ("h2", "h3", "dolearn", "mark", "reveal"):
            close_rail()
            parts.append(render_nodes([node], images))
        elif step is not None:
            step.append(node)
        else:
            parts.append(render_nodes([node], images))
    close_rail()
    return "\n".join(parts)


def stub_body(chapter, images):
    """A SOLO chapter in a room build: participants inherit its result.
    The chapter's own ✦ checkpoint is the honest summary of what they get."""
    mark = next((n for n in chapter["body"] if n[0] == "mark"), None)
    out = ["<p>This chapter was completed for you before the session. "
           "Your workload arrives with its result already in place:</p>"]
    if mark:
        out.append(render_nodes([mark], images))
    return "\n".join(out)


# ---------------------------------------------------------------- pages

def build_pages(ws, images, mode):
    """The ordered page list: Overview, Setup, the chapters, close."""
    pages = [{
        "route": "#/overview", "pid": "page-overview", "title": "Overview",
        "crumb": None, "kicker": None, "meta": None,
        "body": render_body(ws["overview"], images),
    }]
    if ws["setup"]:
        pages.append({
            "route": "#/setup", "pid": "page-setup", "title": "Setup",
            "crumb": None, "kicker": None, "meta": None,
            "body": render_body(ws["setup"], images),
        })
    for ch in ws["chapters"]:
        stubbed = mode == "room" and ch["solo"]
        meta = " · ".join(x for x in (ch["time"], ch["mode"]) if x)
        if stubbed:
            meta = "done in prep"
        pages.append({
            "route": f"#/{ch['num']}", "pid": f"page-{ch['num']}",
            "title": f"{ch['num']}. {ch['name']}",
            "crumb": f"Chapter {ch['num']}",
            "kicker": f"CHAPTER {ch['num']}",
            "meta": meta,
            "body": (stub_body(ch, images) if stubbed
                     else render_body(ch["body"], images)),
        })
    close_nodes = list(ws["close"])
    close_title = "Close"
    if close_nodes and close_nodes[0][0] == "h2":
        close_title = close_nodes[0][1]     # the first h2 IS the page title
        close_nodes = close_nodes[1:]
    pages.append({
        "route": "#/close", "pid": "page-close", "title": close_title,
        "crumb": None, "kicker": None, "meta": None,
        "body": render_body(close_nodes, images),
    })
    return pages


def render_landing_head(ws, codename):
    name = codename or "‹your-codename›"
    name_cls = "" if codename else " unset"
    stand = (f'<p class="standfirst">{inline(ws["standfirst"])}</p>'
             if ws["standfirst"] else "")
    meta = f'<p class="mast-meta">{inline(ws["meta"])}</p>' if ws["meta"] else ""
    return (
        '<header class="page-head"><h1>'
        f"{esc(ws['title'])}</h1></header>{stand}{meta}"
        f'<p class="codename{name_cls}"><span>CODENAME</span>{esc(name)}</p>')


def render_page_sections(ws, pages, codename):
    out = []
    for k, page in enumerate(pages):
        crumb = ""
        if page["crumb"]:
            crumb = ('<nav class="crumb" aria-label="Breadcrumb">'
                     f'<a href="#/overview">{esc(ws["title"])}</a>'
                     '<span class="crumb-sep">›</span>'
                     f"<b>{esc(page['title'])}</b></nav>")
        if page["pid"] == "page-overview":
            head = render_landing_head(ws, codename)
        else:
            kicker = (f'<p class="kicker">{esc(page["kicker"])}</p>'
                      if page["kicker"] else "")
            meta = (f'<span class="page-meta">{esc(page["meta"])}</span>'
                    if page["meta"] else "")
            head = (f'{kicker}<header class="page-head">'
                    f'<h1>{esc(page["title"])}</h1>{meta}</header>')
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
        meta = f' <span>{esc(p["meta"])}</span>' if p.get("meta") else ""
        parts.append(f'<a class="pager-next" href="{p["route"]}">'
                     f'{esc(p["title"])}{meta} →</a>')
    parts.append("</nav>")
    return "".join(parts)


# ---------------------------------------------------------------- shell

def render_sidebar(pages):
    """The sidebar is the page list, nothing else: Overview, Setup, the
    numbered chapters, the closing page. No ticks, no times, no badges."""
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
<style>
{{CSS}}
</style>
</head>
<body>
{{TOPBAR}}
<div class="shell">
{{SIDEBAR}}
<main>
{{PAGES}}
</main>
</div>
<script>
{{JS}}
</script>
</body>
</html>
"""


def render_document(ws, codename, css, js, images, brand, mode):
    pages = build_pages(ws, images, mode)
    return (TEMPLATE
            .replace("{{TITLE}}", esc(ws["title"]))
            .replace("{{CSS}}", css)
            .replace("{{TOPBAR}}", render_topbar(ws, brand))
            .replace("{{SIDEBAR}}", render_sidebar(pages))
            .replace("{{PAGES}}", render_page_sections(ws, pages, codename))
            .replace("{{JS}}", js))
