"""Workshop IR -> one self-contained HTML page.

One renderer per block type; the shell (topbar, sidebar, pager) knows page
titles and counts, never content. All style lives in assets/*.css, all
behavior in assets/app.js; this module only produces markup.

The step rail: within a page, each command block opens a numbered step and
everything until the next command belongs to it. Derived purely from the
order authored in WORKSHOP-2H.md; the renderer never invents content, only
structure that is already implicit in the sequence.
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
    """Tint verdict words independently of the box they sit in: beat 4's
    expected output is a HOLD, and the word must read as the gate's verdict
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
            out.append(render_aside(node[1], node[2]))
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
    parts = ['<div class="diag">']
    for row in rows:
        cls = DIAG_CLASS[row["glyph"]]
        body = row["text"]
        if row["cont"]:
            body = (body + "\n" if body else "") + "\n".join(row["cont"])
        parts.append(
            f'<div class="diag-row diag-{cls}">'
            f'<p class="diag-label"><span class="diag-mark">{row["glyph"]}'
            f"</span>{esc(sentence(row['label']))}</p>"
            f"<pre>{verdicts(esc(body))}</pre></div>")
    parts.append("</div>")
    return "\n".join(parts)


def render_aside(title, parts):
    out = [f'<div class="aside"><p class="aside-title">'
           f"? {esc(sentence(title))}</p>"]
    for kind, text in parts:
        if kind == "prose":
            out.append(f"<p>{inline(text)}</p>")
        else:
            out.append(f"<pre>{esc(text)}</pre>")
    out.append("</div>")
    return "\n".join(out)


def render_fig(caption, path, images):
    uri = images[path]
    cap = f"<figcaption>{inline(caption)}</figcaption>" if caption else ""
    return (f'<figure><img src="{uri}" alt="{html.escape(caption, quote=True)}">'
            f"{cap}</figure>")


# ---------------------------------------------------------------- steps

def group_steps(nodes):
    """A command opens a step; everything until the next command joins it.
    Content before the first command is the page lead, outside the rail."""
    lead, steps, current = [], [], None
    for node in nodes:
        if node[0] == "cmd":
            current = [node]
            steps.append(current)
        elif current is None:
            lead.append(node)
        else:
            current.append(node)
    return lead, steps


def render_body(nodes, images):
    lead, steps = group_steps(nodes)
    out = [render_nodes(lead, images)]
    if steps:
        out.append('<div class="steps">')
        for k, step in enumerate(steps, 1):
            out.append(
                f'<div class="step"><span class="step-num">{k}</span>'
                f'<div class="step-body">{render_nodes(step, images)}'
                "</div></div>")
        out.append("</div>")
    return "\n".join(out)


# ---------------------------------------------------------------- pages

def short_meta(text):
    return text.replace(" minutes", " min").replace(" minute", " min")


def build_pages(ws, images):
    """The ordered page list: start, eight beats, close (the epilogue)."""
    pages = [{
        "route": "#/start", "pid": "page-start", "title": "Start here",
        "crumb": None, "kicker": None, "meta": None,
        "body": render_body(ws["setup"], images),
    }]
    for act in ws["acts"]:
        first = True
        for beat in act["beats"]:
            meta = " · ".join(x for x in (beat["time"], beat["mode"]) if x)
            if not meta and act["meta"]:
                meta = short_meta(act["meta"])
            nodes = (act["intro"] if first else []) + beat["body"]
            first = False
            pages.append({
                "route": f"#/{beat['num']}", "pid": f"page-{beat['num']}",
                "title": f"{beat['num']}. {beat['name']}",
                "crumb": f"ACT {act['num']}",
                "kicker": f"ACT {act['num']} · {act['name']}",
                "meta": meta, "body": render_body(nodes, images),
            })
    close_title = next((n[1] for n in ws["close"] if n[0] == "h2"), "Close")
    pages.append({
        "route": "#/close", "pid": "page-close", "title": close_title,
        "crumb": None, "kicker": None, "meta": None,
        "body": render_nodes(ws["close"], images),
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
                     f'<a href="#/start">{esc(ws["title"])}</a>'
                     '<span class="crumb-sep">›</span>'
                     f'<span>{esc(page["crumb"])}</span>'
                     '<span class="crumb-sep">›</span>'
                     f"<b>{esc(page['title'])}</b></nav>")
        if page["pid"] == "page-start":
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

def render_sidebar(ws, pages):
    rows = ['<a class="nav-row" href="#/start" data-route="#/start">'
            '<span class="nav-name">Start here</span>'
            '<span class="tick">✓</span></a>']
    for act in ws["acts"]:
        rows.append(
            f'<div class="nav-act"><span class="nav-act-name">ACT '
            f'{act["num"]} · {esc(act["name"])}</span></div>')
        for beat in act["beats"]:
            rows.append(
                f'<a class="nav-row" href="#/{beat["num"]}" '
                f'data-route="#/{beat["num"]}">'
                f'<span class="nav-num">{beat["num"]}.</span>'
                f'<span class="nav-name">{esc(beat["name"])}</span>'
                f'<span class="tick">✓</span></a>')
    return ('<aside id="sidebar"><nav aria-label="Workshop contents">'
            + "".join(rows) + "</nav></aside>")


def render_topbar(ws, pages, brand):
    """brand: {"mark": data_uri, "wordmark": data_uri} from assets/,
    inlined by the build so the file stays self-contained."""
    segs = "".join(f'<span data-route="{p["route"]}"></span>' for p in pages)
    return (
        '<header id="topbar">'
        f'<a class="brand" href="#/start">'
        f'<img class="brand-logo" src="{brand["mark"]}" alt="">'
        f'<span class="brand-name">{esc(ws["title"])}</span></a>'
        '<span id="topbar-here"></span>'
        f'<img class="topbar-wordmark" src="{brand["wordmark"]}" '
        'alt="Commvault">'
        f'<div id="progress" aria-hidden="true">{segs}</div>'
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


def render_document(ws, codename, css, js, images, brand):
    pages = build_pages(ws, images)
    return (TEMPLATE
            .replace("{{TITLE}}", esc(ws["title"]))
            .replace("{{CSS}}", css)
            .replace("{{TOPBAR}}", render_topbar(ws, pages, brand))
            .replace("{{SIDEBAR}}", render_sidebar(ws, pages))
            .replace("{{PAGES}}", render_page_sections(ws, pages, codename))
            .replace("{{JS}}", js))
