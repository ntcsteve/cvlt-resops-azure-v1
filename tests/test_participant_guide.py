"""The participant guide build: content fidelity, codename safety, offline.

These tests pin the contract between WORKSHOP-2H.md (the only authored
content) and the generated one-file HTML guide. They need no tenant and
no network, like everything else in this suite.
"""

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

from guide import parser  # noqa: E402
from guide.build import build  # noqa: E402

MD = REPO / "WORKSHOP-2H.md"
CODENAME = "test-kestrel7"


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    out = tmp_path_factory.mktemp("guide") / "guide.html"
    return build(MD, out, CODENAME)


@pytest.fixture(scope="module")
def page_no_codename(tmp_path_factory):
    out = tmp_path_factory.mktemp("guide") / "guide-placeholder.html"
    return build(MD, out, None)


def bash_fences(text):
    return re.findall(r"```bash\n(.*?)```", text, re.S)


def commands_in(page_html):
    return re.findall(r"<pre><code>(.*?)</code></pre>", page_html, re.S)


def test_structure_seven_chapters_three_solo():
    """Seven chapters, and EVERY ONE OF THEM RUNS A COMMAND.

    There used to be an eighth, "Preparing for the questions", which was the
    only chapter in the guide with no command in it: a facilitator's
    twenty-minute room exercise, complete with a 05/15/05 clock, rendered as
    a self-paced page. Neither AWS nor Google Codelabs has anything like it
    -- a codelab's last step is a zero-duration recap -- and a lone reader at
    11pm was never going to run it. Its takeaways moved to the Wrap-up and
    the exercise moved to FACILITATOR, where the choreography already was.

    The three SOLO chapters are the ones a ROOM never does: the facilitator
    provisions, drills on the projector, and tears down after everyone
    leaves."""
    workshop = parser.group(parser.parse(MD.read_text(encoding="utf-8")))
    parser.check(workshop)
    assert [c["num"] for c in workshop["chapters"]] == [1, 2, 3, 4, 5, 6, 7]
    assert [c["num"] for c in workshop["chapters"] if c["solo"]] == [1, 5, 7]


def test_every_command_lands_byte_identical(page):
    md_text = MD.read_text(encoding="utf-8").replace(
        "<your-codename>", CODENAME)
    rendered = commands_in(page)
    fences = [f.strip() for f in bash_fences(md_text)]
    assert len(fences) == len(rendered)
    import html as html_mod
    rendered_plain = [html_mod.unescape(r) for r in rendered]
    for fence in fences:
        assert fence in rendered_plain, f"command lost in render: {fence!r}"


def test_codename_never_inside_a_command(page):
    for command in commands_in(page):
        assert CODENAME not in command


def test_codename_reaches_the_expected_output_boxes(page):
    assert f"resops-{CODENAME}-rg" in page   # an expected-output box
    assert f"resops-{CODENAME}-vg" in page   # and another


def test_a_build_with_no_codename_leaves_the_placeholder_in_the_boxes(
        page_no_codename):
    """The CODENAME chip on the masthead was removed on 2026-08-19: a label
    restating a value that appears nowhere else on the page. The codename
    still does its real work inside the ✓ expected-output boxes, where a
    participant compares their own resource names, so an un-substituted build
    must still show the placeholder THERE."""
    assert "&lt;your-codename&gt;" in page_no_codename   # HTML-escaped
    assert "CODENAME</span>" not in page_no_codename, "the chip is back"


def test_offline_no_external_references(page):
    assert not re.findall(r'(?:src|href)="https?://', page)


def test_ten_pages_in_order(page):
    routes = re.findall(r'data-route="(#/[a-z0-9]+)"', page)
    unique = list(dict.fromkeys(routes))
    assert unique == ["#/overview", "#/setup", "#/1", "#/2", "#/3", "#/4",
                      "#/5", "#/6", "#/7", "#/close"]


def test_sections_and_page_split(page):
    # the front matter splits into Overview and Setup at '## Setup'
    assert 'data-title="Overview"' in page
    assert 'data-title="Setup"' in page
    assert "What is ResOps?" in page
    # ### sections structure the chapters. They render as <h2 class="section">
    # because the chapter's own title is the page h1: see the outline test.
    for section in ("Provision the service", "The first recovery point",
                    "The gate answers twice", "Verify it is gone",
                    "What you proved", "The one question"):
        assert f'<h2 class="section">{section}</h2>' in page
    # the closing page takes its title from its first h2. TITLE CASE, because
    # the Commvault editorial guide requires it for primary headings and
    # "Capitalize the first character of all hyphenated words when using
    # title case". ### subheads stay sentence case, which the same guide asks.
    assert 'data-title="Wrap-Up"' in page


def test_stray_h2_inside_a_chapter_is_a_loud_error():
    md = ("# T\n\n## Chapter 1 · A\n\ntext\n\n## Oops\n\nmore\n\n"
          "## Chapter 2 · B\n\ntext\n")
    with pytest.raises(SystemExit, match="use '### ' for sections"):
        parser.group(parser.parse(md))


def test_no_facilitator_content(page):
    for marker in ("COUNT TO TEN", "facilitator runbook", "Do not spoil"):
        assert marker not in page


def test_unknown_fence_language_is_a_hard_error(tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_text("# T\n\n```python\nx = 1\n```\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="unknown fence language"):
        parser.parse(bad.read_text(encoding="utf-8"))


def test_every_command_sits_in_exactly_one_step(page):
    n_cmds = page.count('<div class="cmd" data-copy>')
    n_steps = page.count('<div class="step">')
    assert n_cmds == len(commands_in(page))
    assert n_steps == n_cmds, "step rail out of sync with command blocks"


def test_landmarks_present(page):
    assert 'aria-label="Workshop contents"' in page
    assert 'aria-label="Breadcrumb"' in page


def test_missing_image_is_a_hard_error(tmp_path):
    from guide.build import inline_images
    nodes = parser.parse("![cap](images/nope.png)\n")
    with pytest.raises(SystemExit, match="image not found"):
        inline_images(nodes, tmp_path)


@pytest.fixture(scope="module")
def room_page(tmp_path_factory):
    out = tmp_path_factory.mktemp("guide") / "guide-room.html"
    return build(MD, out, CODENAME, mode="room")


def test_room_mode_omits_the_solo_chapters_and_numbers_the_rest_gaplessly(
        room_page):
    """A room does not provision, drill or tear down: the facilitator does, in
    prep. Rendering those chapters as pages gave a room participant a sidebar
    where entries said "nothing here for you", so the room build omits them
    and numbers what remains 1..N."""
    assert "terraform -chdir" not in room_page      # the command, not the word
    assert "op restore" not in room_page
    assert "op teardown" not in room_page
    routes = list(dict.fromkeys(
        re.findall(r'data-route="(#/[a-z0-9]+)"', room_page)))
    assert routes == ["#/overview", "#/setup", "#/1", "#/2", "#/3", "#/4",
                      "#/close"]


def test_the_room_build_loses_no_checkpoint(page, room_page):
    """THE INVARIANT THAT REPLACED A PAGE COUNT.

    Counting pages only proved the two builds were different sizes. What
    actually matters is that omitting a chapter from the room build never
    silently drops what that chapter concluded: every ✦ checkpoint in the solo
    build has to reach the room build too, riding the "You arrive with" band
    on the next rendered page. A checkpoint that vanishes here is content lost
    to a rendering decision, which is the whole failure this guards."""
    marks = lambda html: set(re.findall(r'<p class="mark-title">✦ ([^<]+)</p>',
                                        html))
    missing = marks(page) - marks(room_page)
    assert not missing, f"checkpoints lost from the room build: {missing}"
    assert room_page.count('class="inherited"') == 3


def test_solo_mode_carries_the_full_climb(page):
    assert "terraform -chdir=infra/workloads apply" in page
    assert "op restore infra/workloads" in page


def test_committed_previews_are_fresh(tmp_path):
    """dist/preview*.html are CHECKED IN so the team can open the product
    without building it. A committed page that drifts behind the markdown
    is the two-sources-of-truth bug in its worst form, so staleness is a
    red suite, not a surprise."""
    for name, mode in (("preview.html", "solo"), ("preview-room.html",
                                                  "room")):
        committed = REPO / "dist" / name
        assert committed.is_file(), f"dist/{name} is missing; rebuild it"
        fresh = build(MD, tmp_path / name, None, mode=mode)
        assert fresh == committed.read_text(encoding="utf-8"), (
            f"dist/{name} is stale. Rebuild: python3 tools/guide/build.py "
            f"--out dist/{name} --mode {mode}")


def test_parse_errors_carry_line_numbers():
    md = "# T\n\ntext\n\n```python\nx = 1\n```\n"
    with pytest.raises(SystemExit, match="line 5: unknown fence language"):
        parser.parse(md)


def test_lookalike_glyph_is_a_loud_error_not_a_silent_panel():
    md = "# T\n\n```\n ✅ YOU SHOULD SEE   something\n```\n"
    with pytest.raises(SystemExit, match="line 4: .*looks like a diagnostic"):
        parser.parse(md)


def test_diag_words_in_a_plain_fence_are_a_loud_error():
    md = "# T\n\n```\n YOU SHOULD SEE   something\n```\n"
    with pytest.raises(SystemExit, match="line 4: .*reads like a diagnostic"):
        parser.parse(md)


def test_sentence_case_label_is_a_loud_error_with_the_rule():
    md = "# T\n\n```\n ✓ You should see   something\n```\n"
    with pytest.raises(SystemExit, match="line 4: .*UPPERCASE label"):
        parser.parse(md)


def test_command_without_expected_output_fails_the_build():
    from guide.build import check_expected_output
    md = ("# T\n\n## Chapter 1 · B\n\n"
          "```bash\necho hello\n```\n\nprose but no expected output.\n")
    workshop = parser.group(parser.parse(md))
    with pytest.raises(SystemExit, match="expected-output"):
        check_expected_output(workshop)


def test_the_room_build_folds_the_asides_and_the_solo_build_opens_them(
        page, room_page):
    """WHY THE TWO BUILDS DIFFER IN DENSITY, not just in coverage.

    In a SOLO read the page is the only teacher and every aside must be open.
    In a ROOM the facilitator is the teacher, and several asides ARE their
    lines -- the reveal in Break is the moment the day turns on. Printing it
    beside the command hands the punchline to anyone reading ahead and
    competes with the human for the same fifteen minutes.

    Folded, not deleted: same words, same markdown, one click away."""
    # an open aside is <aside role="note">; a folded one is <details>, which
    # is the interactive-disclosure element and carries its own semantics.
    assert '<aside class="aside" role="note">' in page
    assert '<details class="aside aside-fold">' not in page
    assert '<aside class="aside" role="note">' not in room_page
    assert '<details class="aside aside-fold">' in room_page
    open_titles = set(re.findall(r'<p class="aside-title">\? ([^<]+)</p>', page))
    fold_titles = set(re.findall(
        r'<details class="aside aside-fold"><summary>\? ([^<]+)</summary>',
        room_page))
    # Not equality: the room build also omits the SOLO chapters, so their
    # asides go with them. What must hold is that folding never renames or
    # invents one -- every aside the room shows is an aside the solo build has.
    assert fold_titles and fold_titles <= open_titles, (
        f"folded asides that solo does not have: {fold_titles - open_titles}")


def test_a_diag_description_flows_and_its_quoted_output_does_not(page):
    """THE FULL-WIDTH RULE.

    A ✓ row carries two kinds of text and they must not render the same way.
    The label line is the author's DESCRIPTION of what the participant is
    looking at: prose, so it flows to the content width and rewraps. The
    indented continuation is QUOTED OUTPUT, where line breaks are meaning.

    Rendering both as one <pre> is what made expected-output boxes wrap at the
    ~46 columns they happened to be authored at, inside a container twice that
    wide, breaking sentences mid-clause. This pins the split."""
    row = re.search(
        r'<div class="diag-row diag-yes">.*?a job id, then that job reaching'
        r' its final state.*?</div>', page, re.S)
    assert row, "the backup step's ✓ row is not where this test expects it"
    assert '<p class="diag-text">a job id, then that job reaching its final ' \
           'state</p>' in row.group(0)
    assert "<pre>backup Completed</pre>" in row.group(0)


def test_a_leftover_time_or_mode_badge_in_a_heading_is_a_loud_error():
    """Per-chapter time and mode badges were removed on 2026-08-19: the page
    stopped showing them, so the markdown stopped carrying them. The risk is
    someone re-adding one out of muscle memory and it silently doing nothing,
    which is how a doc grows data nobody maintains. It errors instead, naming
    the offending token."""
    for bad in ("## Chapter 1 · A · ~15 min\n", "## Chapter 1 · A · LIVE\n",
                "## Chapter 1 · A · ~15 min · LIVE · SOLO\n"):
        with pytest.raises(SystemExit, match="takes SOLO and an @icon-name"):
            parser.parse("# T\n\n" + bad + "\ntext\n")


def test_no_page_skips_a_heading_level(page, room_page):
    """THE OUTLINE, pinned as a class of defect rather than an instance.

    Chapter pages used to go h1 -> h3: the page title, then ### sections
    rendered as <h3>, with nothing at level 2. A screen reader announces
    that as a missing section, on all ten chapter pages at once. The
    authoring level stays ### because ## is reserved for page boundaries
    in the dialect; only the RENDER changed.

    Written against every page in both builds, so the next block type that
    emits a heading cannot quietly reintroduce it."""
    for label, html in (("solo", page), ("room", room_page)):
        for section in re.findall(r'<section class="page".*?</section>',
                                  html, re.S):
            title = re.search(r'data-title="([^"]*)"', section).group(1)
            levels = [int(h) for h in re.findall(r"<h([1-6])[ >]", section)]
            previous = 0
            for level in levels:
                assert not (previous and level > previous + 1), (
                    f"{label} build, page {title!r}: heading jumps from h"
                    f"{previous} to h{level}")
                previous = level


def test_the_page_states_that_its_expected_output_is_verified(page):
    """The suite checks every offline command's output against the real tool.
    A reader who does not know that reads a mismatch as the guide being
    wrong, and quietly stops trusting it. The claim is only allowed on the
    page because it is true, and this is what keeps it true."""
    assert "checked against real command output" in page


def test_keyboard_users_can_reach_the_content_and_see_where_they_are(page):
    """A skip link, and a visible focus ring on every interactive element.
    <summary> matters most: the folded asides are the ROOM build's main
    interaction and had no focus style at all."""
    assert '<a class="skip" href="#main">' in page
    assert '<main id="main" tabindex="-1">' in page
    assert "summary:focus-visible" in page


def test_folded_asides_still_print(page, room_page):
    """The ROOM build folds its asides because a facilitator is delivering
    them. Paper has no facilitator, and a closed <details> prints closed, so
    the printed room guide was losing every explanation on the page. Print
    opens everything."""
    for html in (page, room_page):
        assert "details > *:not(summary) { display: block !important; }" in html
    assert ".step, .diag, .cmd { break-inside: avoid; }" in page


def test_every_chapter_runs_at_least_one_command(page):
    """THE PROMISE THE GUIDE MAKES, pinned.

    Every chapter is: run something, compare it to a box, learn one thing.
    The removed chapter 7 broke that promise -- it was thirty minutes of
    writing with no command, the longest chapter in the guide and the only
    one with nothing to run. If a chapter ever again has no command, either
    it is not a chapter or the promise has quietly changed."""
    chapters = parser.group(parser.parse(MD.read_text(encoding="utf-8")))["chapters"]
    for chapter in chapters:
        commands = [n for n in chapter["body"] if n[0] == "cmd"]
        assert commands, (
            f"chapter {chapter['num']} ({chapter['name']}) runs no command. "
            f"Content with nothing to run belongs on the Overview or the "
            f"Wrap-up, not in the numbered path.")


def test_a_list_fence_flows_and_a_plain_fence_does_not(page):
    """THE FULL-WIDTH RULE, second half.

    Most of this guide's list content is a label beside a sentence, not a
    diagram. Authored in a plain fence it rendered <pre>, so it broke
    wherever the author's editor happened to wrap and used about half the
    page. ```list renders the label in a column and the text as <p>, which
    flows and rewraps; a plain fence stays preformatted, because a diagram's
    alignment IS its meaning and reflowing it would destroy it.

    Both must keep working, which is why this asserts on one of each."""
    # a definition list: label in a column, text in flowing paragraphs
    assert '<div class="deflist">' in page
    assert '<span class="dl-key">Air Gap Protect</span>' in page
    assert '<div class="dl-val"><p>The immutable, air-gapped pool' in page
    # a diagram: still preformatted, still scrolls in its own container
    assert '<pre class="panel">' in page
    assert "PRODUCTION PLANE          RECOVERY PLANE" in page


def test_an_unparseable_list_row_is_a_loud_error():
    md = "# T\n\n```list\n a label with no text\n```\n"
    with pytest.raises(SystemExit, match="has no text"):
        parser.parse(md)


def test_an_unknown_fence_language_still_names_list():
    md = "# T\n\n```python\nx = 1\n```\n"
    with pytest.raises(SystemExit, match=r"```bash, ```list, ```list card"):
        parser.parse(md)


# --------------------------------------------------------------------------- #
# COMMVAULT BRAND COMPLIANCE.
#
# Sources: CVLT-Brand-Primer_v1.3 (visual identity) and
# CVLT_Tone-and-Editorial-Style-Guide_DEC-2024 (voice and copy). Both were
# applied on 2026-08-19. These pin the parts a future edit would quietly
# undo -- a font swap, an off-brand hex, a British spelling creeping back.
# --------------------------------------------------------------------------- #
BRAND = {
    "Midnight": "#00053b", "Crocus": "#844896", "Fog": "#eaeaea",
    "White": "#ffffff",
}


def test_the_typeface_is_the_brand_approved_one(page):
    """The primer names Galano Grotesque primary and Arial as "the approved
    system font ... available to use WITHOUT A LICENSE". Galano is a licensed
    webfont and this build fails on any external reference, because the guide
    has to open from file:// with no network. Arial is therefore both the
    compliant choice and the only offline-safe one."""
    assert "--f-sans: Arial, Helvetica, sans-serif;" in page
    assert "-apple-system" not in page, "reverted to a non-brand system stack"


def test_the_palette_is_the_brand_palette(page):
    """Midnight, Crocus and Fog used exactly. Rose and Grass FAIL WCAG AA on
    white at full strength (4.15:1 and 2.70:1), so the verdict colors are the
    lightest shade of each that passes -- a brand-permitted shade, since the
    primer allows "tints and shades of our primary and secondary colors"."""
    for name, hexv in BRAND.items():
        assert hexv in page.lower(), f"{name} {hexv} is no longer in the palette"
    assert "--yes:         #30881c;" in page      # 76% shade of Grass, 4.50:1
    assert "--no:          #db2961;" in page      # 94% shade of Rose,  4.66:1


def test_primary_headings_are_title_case_and_subheads_are_not():
    """The editorial guide: title case for titles and primary headings,
    sentence case for secondary headings and subheads. Chapter names are
    primary; the ### sections inside them are not."""
    text = MD.read_text(encoding="utf-8")
    for name in ("Building the Workload", "Reading the Proof",
                 "Introducing a Compromise", "Choosing a Recovery Point",
                 "Re-Proving Recovery", "Gating the Pipeline", "Cleaning Up"):
        assert f"· {name}" in text, f"chapter heading {name!r} lost title case"
    # and a sample of ### subheads that must NOT be title case
    for sub in ("### Plant the compromise", "### The gate answers twice",
                "### Verify it is gone"):
        assert sub in text, f"{sub!r} should stay sentence case"


def test_no_british_spellings():
    """The editorial guide defers to AP Style, which is US English."""
    text = MD.read_text(encoding="utf-8").lower()
    for word in ("organisation", "programme", "behaviour", "standardised",
                 "datacentre", "centre", "colour", "realise", "analyse"):
        assert word not in text, f"British spelling {word!r} is back"


def test_no_ellipses_except_inside_a_quotation():
    """"Avoid using ellipses unless you are omitting content within a quote."
    The one permitted use is the elided middle of the crosswalk disclaimer."""
    text = MD.read_text(encoding="utf-8")
    for hit in [m.start() for m in re.finditer(r"\.\.\.", text)]:
        window = text[max(0, hit - 90):hit + 20]
        assert "Indicative mapping" in window, (
            f"ellipsis used as a placeholder rather than an omission: "
            f"{text[max(0,hit-50):hit+20]!r}")


def test_the_thesis_is_display_type_not_a_terminal_panel(page):
    """"You gate on tests. You gate on security scans. You do not gate on
    recoverability." is the thesis of the whole workshop -- FACILITATOR says
    to say it in the first five minutes and return to it after every module.
    It was rendering as grey mono in a box identical to every other panel.
    A ```statement fence gives it display type, and the bolded third line
    takes Rose because it is the one that is not true yet."""
    assert '<div class="statement">' in page
    assert "<strong>You do not gate on recoverability.</strong>" in page


def test_each_verdict_row_carries_its_own_verdict_colour(page):
    """The verdict card exists to show that one command gave four opposite
    answers. With every row identical the reader had to parse the words to
    see it; a rule in the verdict's own colour makes the shape visible
    first. Same rule the page already applies to the WORDS PROMOTE and HOLD."""
    assert page.count('class="dl-key dl-yes"') == 2      # two PROMOTEs
    assert page.count('class="dl-key dl-no"') == 2       # two HOLDs


def test_the_overview_masthead_is_flush_with_the_topbar(page):
    """THE ROOT CAUSE, pinned.

    Top spacing used to live on `main`, the shared container, so no single
    page could opt out of it and the Overview's aura band began 20px below
    the topbar -- a white row through what is meant to be one surface. It was
    briefly papered over with `margin: -4px`, which cancelled only half the
    gap. The fix is ownership: TOP SPACING BELONGS TO THE PAGE.

    If a negative margin ever comes back here, something is being
    compensated for instead of fixed."""
    assert "main { padding: 0 40px 64px; }" in page
    assert ".page { padding: 24px 0 24px; }" in page
    overview = page[page.index("#page-overview {"):
                    page.index(".mast {")]
    assert "margin" not in overview, (
        "the Overview page rule has a margin again; the gap should be owned "
        "by .page's padding, not offset by a negative margin")


def test_the_aura_shares_the_topbar_origin(page):
    """WHY THE SEAM EXISTED, pinned.

    The aura was a full-bleed pseudo-element: width 100vw, left 50%,
    translateX(-50%). That centres on the CONTAINING BLOCK, and the block was
    the centred page column, which the 300px sidebar pushes 150px off viewport
    centre -- so the hero sampled a slice of the gradient 150px from the one
    the topbar sampled and the colours disagreed across the seam.

    Both now read the same image from the same origin: the viewport. If a
    pseudo-element with a translateX full-bleed comes back here, the seam
    comes back with it."""
    assert "background-position: calc(-1 * var(--sidebar-w))" in page
    assert "#page-overview::before" not in page, (
        "the aura is a pseudo-element again; it cannot share the topbar's "
        "origin from inside the centred page column")
    assert "'at-overview'" in page      # the router scopes it


def test_the_diagnostic_pair_is_one_instrument_not_three_alerts(page):
    """"✓ YOU SHOULD SEE / ✗ IF NOT is a DIAGNOSTIC PAIR and it must be the
    most visually distinct thing on the page." It was rendering as separately
    rounded, gapped bands, which reads as unrelated alerts that happen to be
    adjacent rather than one instrument attached to the command above it.

    Semantics too: it is the guide's most important component and it used to
    be an unlabelled <div>, so a screen reader announced it as generic
    content."""
    assert '<aside class="diag" role="note">' in page
    assert '<div class="diag">' not in page
    # one border on the container, hairlines between rows, colour per row
    assert ".diag-row + .diag-row { border-top: 1px solid var(--line); }" in page
    assert ".diag-yes { border-left-color: var(--yes);" in page


def test_a_chapter_closes_as_deliberately_as_it_opens(page):
    """The kicker carries an aura accent at the top of a chapter; the ✦
    checkpoint carries the same gradient as a top edge at the end of one. A
    chapter now opens and closes on the same mark."""
    assert ".mark::before" in page
    assert ".kicker::before" in page


def test_sections_are_divided(page):
    """"Section dividers mark topic transitions between documentation
    sections", and they are a different device from a callout. A four-section
    chapter now reads as four sections rather than one scroll."""
    assert "h2.section, .page > h3 { border-top: 1px solid var(--line);" in page
    assert ".dolearn + h2.section, .page-head + h2.section { border-top: 0;" in page
