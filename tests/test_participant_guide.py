"""The participant guide build: content fidelity, codename safety, offline.

These tests pin the contract between WORKSHOP-2H.md (the only authored
content) and the generated one-file HTML guide. They need no tenant and
no network, like everything else in this suite.
"""

import re
import subprocess
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
                    "What you proved", "The question you will be asked"):
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


# The two editorial rules that reach PRINTED output, so they are guarded over
# the whole repo rather than over one file. Both read source, never a snapshot.
#
# The first version of the spelling guard was a nine-word denylist over
# WORKSHOP-2H.md alone. It passed while "authorises" and "practise" were live
# in that very file and shipped into both built guides, because neither word
# was on the list. A denylist can only catch what its author already thought
# of, which is the one thing a guard is for. These are patterns instead: the
# suffix classes that actually separate British from US spelling, plus an
# explicit allowlist for the ordinary English words those suffixes catch.
# A false positive costs one line here, with the word visible. A false
# negative ships.

SOURCE_SUFFIXES = (".md", ".py", ".css", ".yaml", ".yml", ".sh", ".tf",
                   ".json", ".html", ".example")

BRITISH = (
    (r"[a-z]+is(?:e|es|ed|ing|er|ers|able|ables|ability|ation|ations)",
     "-ise/-isable/-isation -> -ize/-izable/-ization"),
    (r"[a-z]+our",                            "-our -> -or"),
    (r"[a-z]+(?:tre|bre)(?:s|d)?",            "-re -> -er"),
    (r"defence|licence|offence|pretence",     "-ence -> -ense"),
    (r"[a-z]+logue",                          "-logue -> -log"),
    (r"[a-z]+ys(?:e|es|ed|ing)",              "-yse -> -yze"),
    (r"(?:cancell|labell|modell|travell|signall|fuell)[a-z]*", "doubled l"),
    (r"fulfil",                               "fulfil -> fulfill"),
    (r"practise[a-z]*",                       "practise -> practice"),
)

# Ordinary English the suffix patterns catch. Every entry is a word that is
# spelled this way in US English too, so flagging it would be the guard's
# error, not the author's.
NOT_BRITISH = {
    "advise", "advised", "advises", "advising", "arise", "arises", "arising",
    "bitwise", "clockwise", "comprise", "comprised", "comprises", "compromise",
    "compromised", "concise", "cruise", "devise", "devised", "disguise",
    "enterprise", "exercise", "exercised", "exercises", "exercising",
    "expertise", "franchise", "guise", "improvise", "improvised", "improvises",
    "improvising", "likewise", "merchandise", "noise", "otherwise", "pairwise",
    "piecewise", "poise", "praise", "precise", "premise", "premises",
    "promise", "promised", "promises", "raise", "raised", "raises", "raising",
    "revise",
    "revised", "rise", "rises", "rising", "stepwise", "supervise", "surprise",
    "advisable", "adviser", "advisers", "disable", "disabled", "disables",
    # SVG spec identifiers, not prose: feTurbulence type="fractalNoise" is
    # spelled this way by the standard and cannot be "corrected".
    "fractalnoise", "turbulence",
    "miser", "raiser", "raisers", "riser",
    "risers", "wiser",
    "surprised", "surprises", "surprising", "wise",
    "are", "before", "core", "explore", "figure", "future", "genre", "here",
    "ignore", "more", "nature", "restore", "score", "store", "structure",
    "there", "were", "where",
    "absence", "cadence", "confidence", "dense", "difference", "evidence",
    "fence", "hence", "inference", "presence", "reference", "sense",
    "sentence", "sequence",
    "contour", "devour", "flour", "four", "hour", "hours", "our", "pour",
    "sour", "tour", "tours", "your", "yours",
    "prologue",
}


def repo_sources():
    """Every file the repo SHIPS and writes prose into.

    Scoped by gitignore rather than by a hand-kept exclusion list, because
    that is already the line between what the repo publishes and what stays
    on one laptop: the facilitator script, the handover and the field notes
    are ignored by design, and a guard that turned them permanently red
    would be a guard people learn to skip. Anything not ignored is checked,
    including a file nobody has staged yet.

    Also skips dist/ (generated: rebuilt and byte-compared separately), the
    walk record and this file, since both QUOTE the words they are about."""
    candidates = [p for p in sorted(REPO.rglob("*"))
                  if p.is_file() and p.suffix in SOURCE_SUFFIXES
                  and ".git/" not in p.relative_to(REPO).as_posix()]
    proc = subprocess.run(
        ["git", "check-ignore", "--stdin"], cwd=REPO, text=True,
        input="\n".join(str(p) for p in candidates), capture_output=True)
    ignored = {line.strip() for line in proc.stdout.splitlines()}
    for path in candidates:
        rel = path.relative_to(REPO).as_posix()
        if (str(path) in ignored
                or rel.startswith("dist/")
                or rel in ("tests/workshop_walk.json",
                           "tests/test_participant_guide.py")):
            continue
        yield rel, path


def test_no_british_spellings():
    """The editorial guide defers to AP Style, which is US English. This
    covers the whole repo because the sweep that prompted it found British
    spellings inside strings the participant reads, not only in prose."""
    found = []
    for rel, path in repo_sources():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern, rule in BRITISH:
            for m in re.finditer(rf"\b(?:{pattern})\b", text, re.I):
                word = m.group(0).lower()
                if word in NOT_BRITISH:
                    continue
                line = text[:m.start()].count("\n") + 1
                found.append(f"{rel}:{line}  {word}  ({rule})")
    assert not found, ("British spellings are back:\n  "
                       + "\n  ".join(found[:20]))


def test_no_em_dashes():
    """"Use an en dash with a space on either side"; the em dash is not in
    the editorial guide at all. Guarded over the repo because the em dashes
    that mattered were inside printed strings, not comments: a reason line,
    a gate message, a crosswalk cell. This guard is the one that was claimed
    to exist in the sweep commit and did not."""
    found = []
    for rel, path in repo_sources():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer("\u2014", text):
            line = text[:m.start()].count("\n") + 1
            found.append(f"{rel}:{line}")
    assert not found, ("em dashes are back; use a spaced en dash:\n  "
                       + "\n  ".join(found[:20]))


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


def test_one_h1_size_and_the_masthead_title_fits_on_one_line(page):
    """The Overview title must not carry its own font-size.

    It did, at 72px, and the masthead grid gives the title 488px while 72px
    needs 747px on one line. It wrapped, and "DevOps Meets ResOps" is THREE
    words, so its only two-line breaks are 472/236 and 236/511 -- neither is a
    rag anyone would set, and text-wrap:balance has nothing to choose between.

    MEASURED IN CHROME at 1512px, 488px of column available:

        48px -> 498px   overflows by 10
        46px -> 477px   11px slack, 2%
        44px -> 457px   31px slack, 7%     <- chosen

    A unit test cannot measure shaped text, so it pins the three inputs that
    measurement depended on. If any of them moves, redo the measurement rather
    than adjusting the number here."""
    import re
    # 1. exactly one h1 size, and the Overview overrides only its color
    m = re.search(r"\nh1 \{ font-size: (\d+)px", page)
    assert m, "the base h1 size is gone"
    assert int(m.group(1)) <= 46, (
        f"h1 is {m.group(1)}px; 48 overflows the masthead column by 10px")
    assert "#page-overview .page-head h1 { color: #ffffff; }" in page, (
        "the Overview title has its own rule again; if it carries a font-size, "
        "the 488px column is what it has to fit")

    # 2. the geometry the measurement assumed
    assert "grid-template-columns: minmax(0, 1fr) minmax(0, 27rem);" in page
    assert "--column:      60rem;" in page or "--column: 60rem;" in page

    # 3. the rest of the scale keeps its ordering
    def size(rx):
        mm = re.search(rx, page, re.S)
        assert mm, f"could not find {rx!r}"
        return int(mm.group(1))
    h1v   = int(m.group(1))
    thesis = size(r"\.statement p \{[^}]*?font-size: (\d+)px")
    h2v    = size(r"\nh2 \{ font-size: (\d+)px")
    deck   = size(r"\.standfirst \{ color: var\(--muted\); font-size: (\d+)px")
    assert h1v > thesis > h2v > deck > 16, "the scale lost its ordering"


def test_the_masthead_owns_the_aura_height_not_the_page(page):
    """The dark surface has to be exactly as tall as the masthead in front of
    it, and the element that guarantees that must be the masthead.

    When the min-height sat on #page-overview, the SECTION filled the aura
    while the masthead inside it stayed short, so the next heading flowed up
    into the dark and rendered navy on navy. Measured at 1280, 1100, 880 and
    600 the first h2 sat 4 to 33px ABOVE the bottom of the gradient.

    Verified in Chrome across 1600, 1512, 1341, 1340, 1280, 1200, 1100, 900,
    881, 880, 768, 600, 430 and 390: a uniform 52px gap between the aura and
    the first heading, the transcript card inside the gradient at every one,
    the title on one line at every one, and no horizontal overflow."""
    assert "min-height: calc(var(--aura-h) - var(--topbar-h));" in page
    mast = page.index(".mast {")
    assert "min-height: calc(var(--aura-h) - var(--topbar-h));" in page[mast:mast + 400], (
        "the aura's min-height is not on .mast; if it moves back to the page, "
        "body text renders on the dark band again")
    assert "#page-overview {\n  padding-top: 0;" in page
    ov = page.index("#page-overview {")
    assert "min-height" not in page[ov:ov + 160], (
        "#page-overview has a min-height again")
    # the masthead splits only while the column is at full measure
    assert "@media (max-width: 1340px) {" in page


def test_the_aura_is_dithered_because_this_guide_gets_projected(page):
    """A two-stop gradient in 8-bit sRGB bands where it crosses hue, and a
    projector crushes the bottom two stops, so steps invisible on a laptop
    become stripes on a wall. Three defences, all offline: oklab
    interpolation, extra stops, and feTurbulence noise as a data URI."""
    assert "in oklab" in page, "the aura ramps are back on sRGB interpolation"
    assert "feTurbulence" in page, "the dither layer is gone"
    assert "data:image/svg+xml" in page
    assert 'href="http' not in page and 'src="http' not in page


def test_the_tracking_ladder_covers_the_middle_of_the_scale(page):
    """Arial is spaced for roughly 12px, so every size away from that needs a
    correction. This ladder was half-built: the two display sizes and the
    uppercase labels were tracked and 22/19 carried nothing, which is where
    most of the page lives."""
    assert "h1 { font-size: 44px; font-weight: 700; letter-spacing: -0.022em; }" in page
    assert "letter-spacing: -0.011em;" in page, "h2 is untracked again"
    assert "letter-spacing: -0.005em;" in page, "the standfirst is untracked again"


def test_every_chapter_strip_actually_RENDERS_as_a_strip(page):
    """The companion to the markdown test below, and the one that was missing.

    The parser identifies the chapter strip by its FIRST label. That label was
    DO. On 2026-08-20 STAGE was added above it, the `^DO\\s{2,}` match stopped
    firing, and all seven strips silently fell through to a plain <pre> panel:
    no accent labels, no grid, monospace. It shipped in two commits.

    The five-row test passed the whole time, because it reads WORKSHOP-2H.md
    and never looked at the HTML. A test that reads the source cannot catch a
    rendering regression. This one reads the render."""
    assert page.count('<div class="strip">') == 7, (
        "a chapter strip is not rendering as a strip; the parser identifies "
        "it by its first label, so renaming that label breaks the match")
    assert '<pre class="panel">STAGE' not in page, (
        "a strip fell through to a plain panel")
    for label in ("STAGE", "EXERCISE", "LEARN", "RULE", "NEXT"):
        assert f"<span>{label}</span>" in page, f"{label} is not a strip label"


def test_every_checkpoint_title_is_distinct():
    """Each chapter ends on a ✦ card naming what the reader just did.
    Chapters 5 and 7 both said WHAT YOU JUST CLOSED until 2026-08-20, which
    reads as a copy-paste rather than as a summary of two different things."""
    import re
    md = MD.read_text(encoding="utf-8")
    titles = re.findall(r"✦ (WHAT YOU JUST [A-Z]+)", md)
    assert len(titles) == 7, f"expected 7 checkpoints, found {len(titles)}"
    dupes = [x for x in set(titles) if titles.count(x) > 1]
    assert not dupes, f"duplicate checkpoint titles: {dupes}"


def test_the_concepts_sit_with_the_commands_that_prove_them():
    """Moved on 2026-08-20. The Overview used to carry three arguments a
    reader could not evaluate yet: the three planes, the shift-left table and
    the portability caveat. It ran to 771 words with nothing to do in it,
    against 203 words and five commands in chapter 1.

    Each now sits where it is earned. The planes open chapter 1, which builds
    them. The shift-left table opens chapter 6, which performs the fourth
    one. Portability sits in the Wrap-Up, where it becomes a decision."""
    md = MD.read_text(encoding="utf-8")
    overview = md[:md.index("## Setup")]
    ch1 = md[md.index("## Chapter 1"):md.index("## Chapter 2")]
    ch6 = md[md.index("## Chapter 6"):md.index("## Chapter 7")]
    wrap = md[md.index("## Wrap-Up"):]

    assert "PRODUCTION PLANE" in ch1, "the planes diagram left chapter 1"
    assert "PRODUCTION PLANE" not in overview, "the planes are back on the Overview"
    assert "SHIFTED LEFT ALREADY" in ch6, "the shift-left table left chapter 6"
    assert "SHIFTED LEFT ALREADY" not in overview
    assert "What transfers, and what does not" in wrap
    assert "portable" not in overview, "the portability caveat is back on the Overview"

    # PROSE words, fences excluded, measured the way the 771 -> 468 figure was
    prose = re.sub(r"```.*?```", "", overview, flags=re.S)
    prose = "\n".join(l for l in prose.split("\n") if not l.startswith(("#", ">")))
    words = len(prose.split())
    assert words < 560, (
        f"the Overview is back up to {words} prose words, from 468; it is the "
        f"one page with nothing to do in it, so it is the one that must stay "
        f"short. Put the argument next to the command that proves it.")


def test_every_chapter_carries_the_same_five_row_unit():
    """THE PATTERN. Every chapter head is STAGE / DO / LEARN / CLAIM / NEXT,
    in that order, with no exceptions.

    STAGE names which of the engine's own six stages the chapter moves, using
    the words the tool prints, so `blocked at Scan` in output and `STAGE Scan`
    in the head are visibly the same thing. Two chapters legitimately move
    nothing and say so; naming them is stronger than fudging them.

    NEXT is the adoption path, distributed. Before this existed, the only
    thing a participant could do on Monday was a single block at minute 118,
    when they are tired and half the room has gone. Seven small commitments
    beat one large ladder, and the closing list is now a collection of things
    they already agreed to rather than new information."""
    import re
    md = MD.read_text(encoding="utf-8")
    heads = re.findall(r"^## Chapter \d+ · .+?$\n\n```\n(.*?)```", md, re.S | re.M)
    assert len(heads) == 7, f"expected 7 chapters, found {len(heads)}"
    for i, body in enumerate(heads, 1):
        labels = re.findall(r"^ ([A-Z]+)\s{2,}", body, re.M)
        assert labels == ["STAGE", "EXERCISE", "LEARN", "RULE", "NEXT"], (
            f"chapter {i} strip is {labels}, not the five-row unit")


def test_the_next_rows_and_the_closing_path_are_the_same_promises():
    """The six steps in "What you do next" must be the NEXT rows the reader
    already met, not a fresh list invented at the end. If a NEXT row changes
    and the closing path does not, the workshop promises one thing per
    chapter and a different thing at the close."""
    md = MD.read_text(encoding="utf-8")
    close = md[md.index("### What you do next"):]
    for phrase in ("Read one workload's real state",
                   "Read the bar it is judged against",
                   "Scan one existing backup",
                   "Ask which recovery point you would pick",
                   "Run one drill that produces an attestation",
                   "Add one required check, with a ratchet"):
        assert phrase in close, f"the closing path lost {phrase!r}"
    assert "above this line" not in close  # the permission line is prose now
    assert "Steps one to four you can do this week, alone" in close, (
        "the closing path no longer says where the free part stops")


def test_the_domains_use_commvault_canon(page):
    """Commvault's framework papers say Recovery assurance and Resilience
    measurement. Their marketing pages say Resilience assurance and
    Resilience measurements, and one blog contradicts itself on the plural
    inside a single page. We follow the papers."""
    assert "Recovery assurance" in page
    assert "Resilience measurement" in page
    assert "Resilience assurance" not in page, "that is the marketing name"
    assert "Resilience measurements" not in page, "the papers use the singular"
    assert "Resilience through repetition" not in page, "that name was ours"


def test_sections_are_divided_by_space_not_by_a_rule(page):
    """A topic transition is still marked -- a four-section chapter must read
    as four sections rather than one scroll -- but it is marked with silence
    rather than with a hairline. A rule that only separates is a rule the eye
    has to filter out. This replaced the border-top device on 2026-08-19.

    The hairlines that SURVIVE are the ones that carry meaning, so this also
    pins that they did not get swept away with it."""
    assert "h2.section, .page > h3 { margin-top: 64px; }" in page
    assert ".strip + h2.section, .page-head + h2.section { margin-top: 10px; }" in page
    assert "h2.section, .page > h3 { border-top:" not in page, (
        "the section hairline is back; sections are divided by space now")
    assert ".page-head {" in page and "border-bottom: 1px solid var(--line);\n  padding-bottom" not in page, (
        "the page-head rule is back")
    # The pager KEEPS its rule: it marks where content ends and navigation
    # begins, which is a boundary and not merely a separation.
    assert "margin-top: 40px; padding-top: 16px; border-top: 1px solid" in page
    # meaning-bearing rules, still here
    assert ".aside { border-left: 2px solid var(--line);" in page   # aside
    assert ".diag-yes { border-left-color: var(--yes);" in page     # verdict
    assert ".dl-key.dl-yes { border-left-color: var(--yes); }" in page
