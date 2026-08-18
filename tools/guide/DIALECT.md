# The workshop dialect

The contract between a workshop's markdown and the participant guide it
builds. Every workshop is one markdown file conforming to this dialect,
built by `tools/guide/build.py` into one self-contained HTML file that
opens from `file://` with the network off. The shell (topbar, sidebar,
router, pager, progress, tests) is inherited, never rebuilt.

To start a new workshop: write a conforming markdown file, swap the accent
color in `assets/tokens.css` if the workshop carries a different brand.
That is the whole job.

```
python3 tools/guide/build.py --md THE-WORKSHOP.md \
    --out dist/<codename>.html --codename <codename>
```

## 1. File shape

```
# TITLE                          once, first. names the workshop
                                 everywhere: topbar, tab, breadcrumb
intro prose, blockquote,         the blockquote and the **Level** line
**Level** ... line               render as the landing header
## other headings                Overview-page sections; a heading of
                                 exactly `## Setup` splits the front
                                 matter into the Overview and Setup pages
## Chapter N · Name · ~Nm · MODE · SOLO
                                 one page per chapter. time, mode
                                 (LIVE / OFFLINE) and SOLO optional
### Section name                 sections INSIDE a chapter: they break
                                 the step rail and structure the page.
                                 A bare `## ` inside a chapter is a
                                 BUILD ERROR (it would start the
                                 closing page); sections are ### only
## first heading after the       the closing page; that first h2 is the
   last chapter                  page's title and sidebar name
```

Every chapter follows one fixed order: DO/LEARN strip, lead prose,
### sections carrying the steps and asides, ✦ checkpoint, pager.
Predictability is the reader's second facilitator. In diagnostic
rows, ✓ quotes output (rendered preformatted, line breaks kept);
✗ and ⏱ are guidance (rendered as flowing prose).

## 1b. Two builds from one file

A chapter tagged `SOLO` is for the self-paced reader (they provision, they
drill). `--mode solo` (default) renders everything; `--mode room` renders
SOLO chapters as inherited stubs: one sentence plus the chapter's ✦
checkpoint as the summary of what participants arrive with. Numbering is
stable across modes. One markdown, zero drift between the two products.

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
``` starting ?!    a collapsed reveal (answers to CHECK YOURSELF
                   questions): closed by default, same body rules
``` starting ✦     a checkpoint card (WHAT YOU JUST …): the chapter's
                   consolidation, and its stub summary in room mode
``` starting DO    the DO/LEARN strip: UPPERCASE label, two+ spaces,
                   text. Opens every chapter
``` anything else  a preformatted ASCII panel, shown verbatim
![caption](path)   a figure. inlined into the file at build time
> quote            a blockquote
prose              paragraphs with **bold**, *italic*, `code`, [links](x)
````

## 3. The Start page must carry

- What the participant leaves with (the outcome, not the agenda).
- Who it is for (level, duration, audience).
- The offline note: the page works with no network.
- A prerequisite check as a command with its ✓/✗ pair, so the first
  thing anyone does is prove their machine works.
- The codename slot (see §6).

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

## 7. Images

Live in `images/` beside the markdown, referenced by relative path.
Missing image: build fails. Over ~300KB: build warns, compress it.
In the folder but unreferenced: build warns.

## 8. What the build guarantees

- Anything outside the dialect fails loudly with the reason.
- Act and beat counts match the declared structure.
- Every command lands in the page byte-identical to the markdown.
- Every command has its ✓ box (§4) and sits in exactly one step.
- The codename never appears inside a command.
- Zero external references: the file works offline or does not build.
- No facilitator material: the guide renders participant content only.
