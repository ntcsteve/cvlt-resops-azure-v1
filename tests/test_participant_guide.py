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


def test_structure_four_acts_eight_beats():
    workshop = parser.group(parser.parse(MD.read_text(encoding="utf-8")))
    parser.check(workshop)
    assert [len(a["beats"]) for a in workshop["acts"]] == [1, 3, 2, 2]


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


def test_codename_present_in_chip_and_expected_output(page):
    assert f"<span>CODENAME</span>{CODENAME}<" in page  # landing chip
    assert f"resops-{CODENAME}-rg" in page   # beat 4 expected output
    assert f"resops-{CODENAME}-vg" in page   # beat 2 expected output


def test_placeholder_build_shows_placeholder(page_no_codename):
    assert "‹your-codename›" in page_no_codename


def test_offline_no_external_references(page):
    assert not re.findall(r'(?:src|href)="https?://', page)


def test_ten_pages_in_order(page):
    routes = re.findall(r'data-route="(#/[a-z0-9]+)"', page)
    unique = list(dict.fromkeys(routes))
    assert unique == ["#/start", "#/1", "#/2", "#/3", "#/4", "#/5",
                      "#/6", "#/7", "#/8", "#/close"]


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


def test_progress_segments_and_landmarks(page):
    strip = re.search(r'<div id="progress"[^>]*>(.*?)</div>', page).group(1)
    assert strip.count("<span") == 10   # start + 8 beats + close
    assert 'aria-label="Workshop contents"' in page
    assert 'aria-label="Breadcrumb"' in page


def test_missing_image_is_a_hard_error(tmp_path):
    from guide.build import inline_images
    nodes = parser.parse("![cap](images/nope.png)\n")
    with pytest.raises(SystemExit, match="image not found"):
        inline_images(nodes, tmp_path)


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
    md = ("# T\n\n# ACT I · A\n\n**1 minutes**\n\n## Beat 1 · B\n\n"
          "```bash\necho hello\n```\n\nprose but no expected output.\n")
    workshop = parser.group(parser.parse(md))
    with pytest.raises(SystemExit, match="expected-output"):
        check_expected_output(workshop)
