# The workshop dialect

The contract between a workshop's markdown and the participant guide it
builds. Every workshop is one markdown file conforming to this dialect,
built by `tools/guide/build.py` into one self-contained HTML file that
opens from `file://` with the network off. The shell (topbar, sidebar,
router, pager, tests) is inherited, never rebuilt.

To start a new workshop: write a conforming markdown file. `assets/tokens.css`
holds every color, and each value there is a Commvault brand color or a
permitted tint or shade of one, with the reasoning beside it. Change nothing
there without a brand reason.

```
python3 tools/guide/build.py --md THE-WORKSHOP.md \
    --out dist/<codename>.html --codename <codename>
```

## 1. File shape

```
# TITLE                          once, first. names the workshop
                                 everywhere: topbar, tab, breadcrumb
intro prose, blockquote          the blockquote renders as the landing
                                 standfirst. A ```hero fence renders as the
                                 masthead's terminal transcript. Level,
                                 duration and audience belong in a body
                                 section, not the masthead (§3)
## other headings                Overview-page sections; a heading of
                                 exactly `## Setup` splits the front
                                 matter into the Overview and Setup pages
## Chapter N · Name · SOLO       one page per chapter. SOLO is the ONLY
                                 tag and it is optional. Per-chapter time
                                 and mode badges were removed 2026-08-19;
                                 a heading carrying either is a build
                                 error, not a silent no-op
### Section name                 sections INSIDE a chapter: they break
                                 the step rail and structure the page.
                                 A bare `## ` inside a chapter is a
                                 BUILD ERROR (it would start the
                                 closing page); sections are ### only
## first heading after the       the closing page; that first h2 is the
   last chapter                  page's title and sidebar name
```

Every chapter follows one fixed order: DO/LEARN/CLAIM strip, lead prose,
### sections carrying the steps and asides, ✦ checkpoint, pager.
Predictability is the reader's second facilitator. In diagnostic
rows the LABEL LINE is description and flows to the full content width;
the indented continuation under a ✓ is quoted output and stays
preformatted, because there line breaks are meaning. ✗ and ⏱ are
guidance throughout and flow.

## 1b. Two builds from one file

A chapter tagged `SOLO` is for the self-paced reader (they provision, they
drill, they tear down). `--mode solo` (default) renders everything.
`--mode room` does NOT render SOLO chapters at all: each one's ✦ checkpoint
rides on the next rendered page under a "You arrive with" band, and the
remaining chapters are numbered 1..N so the sidebar has no gaps. A trailing
SOLO chapter hands its checkpoint to the closing page. One markdown, zero
drift, and a test pins that no checkpoint is lost in the swap.

The two builds also differ in DENSITY. `?` asides render open in solo,
where the page is the only teacher, and folded in room, where the
facilitator is: several asides are their lines, and printing them beside
the command hands the punchline to anyone reading ahead.

The parser rejects anything outside this dialect with the reason and the
place. A page that is awkward to express is a dialect gap: extend the
parser, never hand-edit the HTML.

## 2. Block types

````
```bash            a participant command. gets a terminal block with a
                   copy button; opens a numbered step on the page
``` starting ✓✗⏱   the diagnostic rows: ✓ expected output, ✗ what to do
                   if not, ⏱ how long it takes. THE SYNTAX IS EXACT:
                   the glyph must be ✓ ✗ or ⏱ (not ✅ ❌ ✔), the label
                   is UPPERCASE, label and text are separated by TWO or
                   more spaces, continuation lines are indented under
                   the text. Getting any of this wrong is a build error
                   with the line number, never a silently wrong page
``` starting ?     a quiet aside (why this matters, UNDER THE HOOD).
                   title on the first line, prose and indented
                   pre-chunks after
``` starting ?!    a collapsed reveal: closed by default, same body rules
``` starting ✦     a checkpoint card (WHAT YOU JUST …): the chapter's
                   consolidation, and the summary a room inherits when the
                   chapter itself is not rendered
``` starting DO    the DO/LEARN/CLAIM strip: UPPERCASE label, two+ spaces,
                   text. Opens every chapter. DO is what their hands do,
                   LEARN is the mechanism, CLAIM is the sentence they can
                   use in a design review afterwards
```list            a definition list: `label  text` rows, label in a mono
                   column, text as PROSE that flows and rewraps. Use it for
                   anything that is a label beside a sentence; a plain fence
                   would render it preformatted and break it wherever the
                   author happened to wrap. Indent to continue a row; a
                   blank line inside a row starts a new paragraph
```list card       the same, in a card. Use it once, for the thing the page
                   is actually about
@icon-name         an optional prefix on a `list` row: attaches an official
                   Commvault icon (assets/icons/). Explicit in the markdown
                   on purpose, because an icon chosen by a lookup table in
                   the build is a second home for the author's decision
```statement       display type. For the one or two lines the workshop
                   exists to make somebody repeat. Inline markup is
                   processed, so **bold** carries the punch line
```hero            a terminal transcript for the masthead: one per workshop,
                   authored in the front matter, rendered beside the title
                   rather than in the body. A `$` opens a command line;
                   every other line is output
``` anything else  a preformatted ASCII panel, shown verbatim. For DIAGRAMS
                   and TABLES, where the alignment is the meaning
![caption](path)   a figure. inlined into the file at build time
> quote            a blockquote
prose              paragraphs with **bold**, *italic*, `code`, [links](x)
````

## 3. The Start page must carry

- What the participant leaves with (the outcome, not the agenda).
- Who it is for: level, duration, audience. In a body section, not the
  masthead -- the masthead carries the title, the standfirst and the
  ```hero transcript, and nothing else.
- The offline note: the page works with no network.
- A prerequisite check as a command with its ✓/✗ pair, so the first
  thing anyone does is prove their machine works.

## 4. Commands: enforced by the build

Every command must be followed by a ✓ expected-output box before the
next command begins. The build fails otherwise, naming the command.
Participants compare, they never guess.

- ✗ rows are strongly recommended wherever failure is plausible, and
  every ✗ names a recovery action. "Ask the facilitator" is a valid
  action; silence is not.
- ⏱ rows wherever a command runs long enough that someone might kill it.
- Commands are identical for every participant. The codename never
  appears in a command; the build refuses it (see §6).

## 5. The closing page must carry

- What is honestly not solved. Admitting the gaps is part of the method.
- One next action. One, not three.

## 6. Per-participant builds

`<your-codename>` anywhere in the markdown is replaced by `--codename`
at build time. Use it in expected-output boxes so participants see their
own resource names. One build per participant. The build fails if the
codename leaks into a command block.

## 7. Images and icons

Images live in `images/` beside the markdown, referenced by relative path.
Missing image: build fails. Over ~300KB: build warns, compress it. In the
folder but unreferenced: build warns.

Icons live in `assets/icons/` and are official Commvault icons only, in the
MIDNIGHT variant, because the color budget reserves crocus for interaction
and an icon is content. They are inlined as data URIs rather than as markup,
since the source files share ids and a `.cls-1` class and would collide.
An unknown `@name` fails the build; an unreferenced icon warns.

## 8. What the build guarantees

- Anything outside the dialect fails loudly with the reason.
- Chapters are numbered 1..N in order, or the build fails.
- A chapter heading carrying anything but SOLO fails the build.
- An unknown fence language, a mistyped diagnostic glyph, a sentence-case
  diagnostic label, a list row with no text and an unknown @icon are all
  build errors with a line number.
- Every command lands in the page byte-identical to the markdown.
- Every command has its ✓ box (§4) and sits in exactly one step.
- The codename never appears inside a command.
- Zero external references: the file works offline or does not build.
- No facilitator material: the guide renders participant content only.

## 9. What the build does NOT check, and the suite does

Two editorial rules hold over everything this repo ships, including your
markdown. The BUILD does not enforce them, so a page with either will build
happily and the SUITE will go red:

```
no em dashes        Use a spaced en dash where a sentence breaks, or a
                    period, a comma, or a rephrase. The em dash is not in
                    the Commvault editorial guide at all
US spelling         The guide defers to AP Style. color, center, analyze,
                    catalog, program, license, labeled, authorize
```

Both live in `tests/test_participant_guide.py` as `test_no_em_dashes` and
`test_no_british_spellings`. They are PATTERNS over the suffix classes that
separate British from US spelling, not word lists, because the word list they
replaced let two British spellings through into both built guides on
2026-08-19, for the ordinary reason: it only held words somebody had already
thought of. Neither offending word is reproduced here, because this file is
covered by the same guard.

If one flags a word that is correct English, add it to `NOT_BRITISH` with the
word visible on its own line. That is the cheap direction to be wrong in.

Scope is every file git does not ignore, so a new workshop markdown is covered
the moment it exists, before anyone stages it.
