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

Every chapter follows one fixed order: the five-row strip, lead prose,
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
``` starting ?     a quiet aside (why this matters, HOW IT WORKS).
                   title on the first line, prose and indented
                   pre-chunks after
``` starting ?!    a collapsed reveal: closed by default, same body rules
``` starting ✦     a checkpoint card (WHAT YOU JUST …): the chapter's
                   consolidation, and the summary a room inherits when the
                   chapter itself is not rendered
``` starting STAGE the chapter strip: UPPERCASE label, two+ spaces, text.
                   Opens every chapter, five rows, always in this order:

                     STAGE     which of the engine's own six stages this
                               chapter moves, in the words the tool prints
                     EXERCISE  what their hands do
                     LEARN     the mechanism
                     RULE      the invariant that follows, which they can
                               apply afterwards. It must be true and
                               applicable, not merely quotable
                     NEXT      the one thing to do in their own estate

                   THE PARSER IDENTIFIES THIS BLOCK BY ITS FIRST LABEL. It
                   used to be DO; STAGE was added above it on 2026-08-20,
                   the match stopped firing, and seven strips silently
                   rendered as plain panels for two commits. If you rename
                   the first row, change parser.py in the same commit
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

- What was proven, recapped against executed output.
- The workshop's conclusion: what the day means for how the reader
  already works. A recap that never concludes is scrollback.

Two earlier requirements were removed on 2026-08-20: the honest-limits
section and the one-next-action prompt. Scope honesty lives in the
toolkit's public docs (README, RESOPS.md); adoption steps live in each
chapter's NEXT row, in RESOPS.md, and on worksheet 6 for a room. Do not
reintroduce either on the closing page from memory.

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

## 9. How to write it

The dialect decides the shape. This decides the prose, and it exists because
the guide was rewritten three times in one day before anyone wrote it down.

MEASURED AGAINST TWO REAL CORPORA, not against taste. AWS lab bodies
(disaster-recovery.workshop.aws, eksworkshop.com) run a mean of 20.7 words
per sentence, median 19. Google Codelabs runs 18.9 and 16. In both, roughly
18% of sentences are under ten words. Neither has a long-then-punchy rhythm;
both are a flat band. Ours was at 30% and read as an essay.

```
 TARGET             mean 17-19 words, median 16, about 18% under ten
 A SHORT SENTENCE   appears when the thought is short, never when the
                    paragraph needs a beat
 NO METAPHOR        Google's style guide is categorical: "Don't use
                    metaphors, and don't use a term in a metaphorical
                    sense." Not soften. Delete
 NO APHORISM        neither corpus contains a single sentence written to be
                    remembered. The RULE row is the ONE exception, because
                    being carried away is its job
 NO STAGE DIRECTION "Now look at", "Then read", "Now ask" - the reader is
                    already looking
 NO PREDICTION      "you will find", "you will be asked" - unverifiable, and
                    it tells someone what they are about to feel
 NO SELF-NARRATION  "this part is deliberately calm" describes our pacing to
                    a reader who came to prove a workload recovers
 WHY IS A CLAUSE    weld it to the instruction with because / so that / this
                    means. Never a paragraph of build-up. Anything longer
                    goes in a ? aside
 OPEN WITH EITHER   a definition, or a state transition ("now that X, it is
                    time to Y"). AWS reuses one frame across unrelated labs
                    rather than crafting each opening
 REPEAT YOUR STOCK  the canonical set is below. Both corpora treat
   PHRASES          consistent repetition as a feature
```

The stock phrases, canonical. These are the sentences WORKSHOP-2H.md
already repeats; reuse them before inventing a near-synonym, so workshop
number two sounds like workshop number one without anyone trying to:

```
 THE DIAGNOSTICS     ✓ YOU SHOULD SEE · ✗ IF NOT · ⏱ HOW LONG
 READING OUTPUT      Compare, do not guess.
 A BENIGN WAIT       Waiting for one is normal and not a failure.
                     DO NOT KILL IT.
 THE MEDIA AGENT     the shared worker that moves the data
 A GUEST-AGENT CALL  this runs through the Azure guest agent, which is a
                     single blocking call that reports once at the end
                     rather than streaming
 IN A ROOM           "In a room, ask now rather than when the first
                     command runs" and "tell the facilitator your
                     codename rather than debugging it yourself"
```

Chapter 5 is the house model: 45 words of prose for four commands, section
headings that are plain verbs, one paragraph of context. Edit toward it.

BANNED WORDS, from Google's word list: simply, simple, easily, just, please,
leverage, utilize. Also no exclamation marks.

## 10. What the build does NOT check, and the suite does

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
