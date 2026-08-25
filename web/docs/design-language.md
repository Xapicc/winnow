# winnow — design language

This file is the contract. Later runs read *only* this file for style decisions: if a
rule is not written here it is not a rule, and if a rule here is wrong it gets changed
here first and in the code second.

The brief in one line: **a terminal that a designer got hold of.** Monospace, near-black,
one accent, texture you have to look for. Restraint is the whole point — the moment a
screenshot reads as a 2013 "hacker" theme, the effect has failed.

The site is built to the same shape as UsageFoundry's, whose own contract is at
`Xapicc/UsageFoundryWeb:docs/design-language.md`. It is not that file with the hex codes
swapped. The accent is orange rather than blue, every contrast ratio below was recomputed
against the new colours rather than carried across, and two rules that no longer hold under
an orange brand — the amber signal, and the mark's provenance — are rewritten here rather
than inherited.

---

## 1. Palette

Dark only. There is no light theme and the site does not respond to
`prefers-color-scheme` — the near-black canvas *is* the design.

All tokens live in `app/globals.css`, declared inside Tailwind v4's `@theme` block so
each one is simultaneously a CSS custom property and a utility class
(`--color-canvas` → `bg-canvas`, `text-canvas`, `border-canvas`).

| Token | Hex | Role |
|---|---|---|
| `--color-canvas` | `#0a0a0b` | page background, and the text colour on filled accent |
| `--color-inset` | `#070708` | recessed wells: terminal blocks |
| `--color-surface` | `#121215` | raised panel one step up from canvas |
| `--color-surface-2` | `#17171b` | panel header strips, hover fills |
| `--color-line` | `#23232a` | default rules, panel frames |
| `--color-line-strong` | `#33333d` | emphasised rules, focused frames |
| `--color-fg` | `#e9e9ec` | body and heading text |
| `--color-fg-muted` | `#9b9ba4` | secondary text, captions, nav at rest |
| `--color-fg-faint` | `#6e6e78` | decoration only — see the contrast rule below |
| `--color-accent` | `#ff7a1a` | the one dominant accent |
| `--color-accent-deep` | `#e8621f` | ASCII art, the terminal well's spine, borders |
| `--color-ok` | `#30d158` | signal green — meters and states only |
| `--color-danger` | `#ff617f` | signal red — failure states only |

The greyscale is UsageFoundry's, unchanged and unrecomputed only because the numbers do
not depend on the accent. **Everything with a hue in it was re-derived.**

winnow has no product colour to inherit. There is no icon, no SVG and no brand hex
anywhere in `Xapicc/winnow` — the accent pair was chosen here, for this site, against the
contrast floor below. `#ff7a1a` is a saturated orange at hue 25°; `#e8621f` is the same
family five degrees redder and a step down in luminance.

### Measured contrast

Computed against `--color-canvas` `#0a0a0b` and `--color-surface` `#121215` (WCAG 2.1
relative luminance). **These are winnow's own measurements. Do not copy them from the
reference site and do not carry them forward if a token changes** — a hue shift of ten
degrees moves these numbers by more than the AA margin.

```
fg           #e9e9ec   16.33 : 1  canvas    15.43 : 1  surface
fg-muted     #9b9ba4    7.18 : 1             6.78 : 1
fg-faint     #6e6e78    3.92 : 1             3.71 : 1
accent       #ff7a1a    7.59 : 1             7.17 : 1
accent-deep  #e8621f    5.84 : 1             5.52 : 1
ok           #30d158    9.79 : 1             9.25 : 1
danger       #ff617f    6.85 : 1             6.47 : 1
```

Contrast is symmetric, so the accent's 7.59:1 against canvas is also **canvas text on a
filled accent block at 7.59:1** — which is the direction the primary button spends. Two
more measured pairs that decide rules below:

```
canvas on accent       #0a0a0b on #ff7a1a   7.59 : 1   the filled button, at rest
canvas on accent hover #0a0a0b on #ff8d3a   8.60 : 1   never a regression
white  on accent       #ffffff on #ff7a1a   2.15 : 1   fails everything
white  on accent-deep  #ffffff on #e8621f   3.39 : 1   fails AA
```

Rules that follow from those numbers, and they are not negotiable:

- **`--color-fg-faint` never carries information.** 3.92:1 fails AA for body text. It is
  for box-drawing frames, grid lines, ASCII filler and disabled glyphs. If a sentence has
  to be read, it is at least `--color-fg-muted`. The rule is easy to break by eye, because
  3.92:1 looks like a tasteful grey on a good monitor. Every use of the token is inside an
  `aria-hidden` element — frames, rules, the bracket glyphs on a ghost button, and the
  `01`–`06` ordinals on the home page, which are decoration duplicating a visual order and
  are not announced.
- **White is never placed on either accent.** 2.15:1 and 3.39:1. A filled accent control is
  `--color-accent` with `--color-canvas` text → 7.59:1. Dark-on-bright is also the more
  terminal-looking of the two, so this costs nothing. The rule is *stronger* here than on
  the blue site, where white on the deep accent measured 3.85:1 — an orange is a
  high-luminance hue and there is simply no room above it.
- `--color-line` at 1.27:1 against canvas is a *hairline*, not a border you can read at a
  glance. That is intended. Where a boundary must be perceivable, use
  `--color-line-strong` or a box-drawing character, which carries shape as well as tone.

### The amber that is not here

The reference reserves `--color-warn` `#ff9f0a` for meters and status. **There is no
`--color-warn` on this site, and that is the accent's fault.**

`#ff9f0a` is hue 36.5°. `--color-accent` is hue 25°. Eleven degrees apart, both saturated,
both high-luminance: side by side on a near-black canvas they are the same colour, and a
reader has no way to tell "this is a warning" from "this is the brand". Re-hueing the
warning does not fix it either — pushing it to yellow lands at ~50°, still inside the
family, and pushing it far enough to be unambiguous makes it a second brand colour, which
§1's one-accent budget forbids more strongly than it forbids a missing signal.

So amber is dropped, and the third state is carried by the two things that already work:

- **Indeterminate is `--color-fg-muted` plus the `╱` hatch** from §3. The reference already
  reserves that glyph for "unknown / indeterminate" fill; here it is the whole signal
  rather than an accompaniment to a colour.
- **Shape carries status anywhere colour would have.** Use a distinct glyph (`●`, `▲`, `■`,
  `─`) beside the tone, so the page survives greyscale and colour-blind reading. This was
  already the rule; with two signal colours instead of three it is load-bearing.

This suits what winnow actually has to say. Its three states are *measured*, *modelled* and
*not built yet* — and "modelled, not billed" is an indeterminate, not a warning. There was
never a real amber on this site to lose.

`components/AsciiFigure.tsx` therefore has no `warn` tone. Adding one back means changing
this section first.

### Colour is a signal

Most of the page is greyscale. The budget is roughly: **one accent element per
viewport-height of scroll.** Green and red are reserved for status glyphs and the specific
facts they describe — a green tick that means nothing is worse than no tick. Never colour a
decoration with `--color-ok` because it looks nice there.

The wordmark is the largest accent object on the site and it spends the hero's whole
budget on its own. That is why the mark in §4 is an outline and not a filled block: the
first draft filled 11 × 5 characters with `█`, and at hero size it was a slab of orange
that left nothing for anything else above the fold.

---

## 2. Type

One family, everywhere: **JetBrains Mono**, variable weight axis 100–800, self-hosted.

- Subset committed at `app/fonts/JetBrainsMono-Variable-subset.woff2` (32 KB), loaded via
  `next/font/local` in `app/layout.tsx`, exposed as `--font-mono` and as Tailwind's
  `--font-mono` theme key. **Licence beside it in `JetBrainsMono-OFL.txt` (SIL OFL 1.1),
  and it does not travel separately from the font.**
- The subset covers `U+0020–007E`, selected punctuation and arrows, **`U+2500–257F` box
  drawing** and **`U+2580–259F` block elements**. The Google-Fonts `latin` subset does
  *not* contain those two ranges — that is why the font is built from the upstream release
  rather than pulled from `next/font/google`. If a later run needs a character outside the
  subset, re-cut the font; do not let it fall back, because a fallback glyph breaks the
  grid.
- **Every glyph in the file has advance width 600/1000 = `0.6em`.** All character-grid
  arithmetic on this site depends on that constant.
- No italics. The italic face is not shipped; use weight or colour for emphasis instead of
  letting the browser synthesise an oblique.

There is no OpenGraph card yet, and therefore none of the reference's Satori caveat. The
Twitter card is `summary` rather than `summary_large_image` for exactly that reason: a
large-image card with no image is a broken card. A run that adds `app/opengraph-image.tsx`
changes that line in `app/layout.tsx` in the same commit.

### Scale

Tight tracking, generous leading. Sizes are px because the grid is px.

| Token | Size / line | Use |
|---|---|---|
| `--text-micro` | 11 / 16 | meta rows, kickers, footer legalese |
| `--text-small` | 13 / 20 | captions, table cells, nav |
| `--text-body` | 15 / 24 | body copy. The default. |
| `--text-lead` | 18 / 28 | the one-line product statement, section intros |
| `--text-h3` | 20 / 28 | panel and subsection headings |
| `--text-h2` | 26 / 34 | section headings |

Tracking: `-0.01em` at body and below, `-0.02em` at `--text-h2`/`--text-lead`,
`0.14em` for uppercase kickers and nav (uppercase mono needs the air back).
Weights: 400 body, 500 emphasis and nav, 600 headings, 700 only inside ASCII art.
Never bold a whole sentence.

There is no display type. **The largest thing on any page is ASCII art**, and its size is
computed from the grid, not chosen from this scale.

### Measure

Body copy is capped at `68ch`. Two-column areas are `34ch` each. Never set a paragraph
wider than `72ch` — mono is wide, and a full-bleed mono paragraph is unreadable.

---

## 3. The character grid

The layout snaps to characters, not to an arbitrary 8px rhythm.

```
--ch : 0.6em          one column, exact for this font
--lh : 1.6            one row  = 1.6 × font-size
```

- Horizontal measures that describe *content* are in `ch`: `68ch` measure, `34ch` column,
  `2.5ch` padding inside a frame. Use Tailwind's arbitrary values (`px-[2.5ch]`,
  `gap-[3ch]`) rather than inventing spacing tokens.
- Vertical rhythm uses Tailwind's default 4px step, in multiples of the 24px body row:
  `py-4` (16), `py-6` (24), `py-8` (32), `py-12` (48), `py-16` (64), `py-24` (96).
  Section padding is `py-16` on a phone and `py-24` at desktop.
- Page gutter: `max(2ch, 4vw)` below `640px`, `max(4ch, 5vw)` above — as `--page-gutter`,
  capped by a `76rem` content column. The mono family is set on `html` as well as `body`
  precisely so that `ch` at `:root` is a real column and not the fallback font's `0`.

`ch` resolves against the *element's own* font-size. That is fine for text but a trap for
character art, whose font-size is computed down to fit its container: a `w-[3ch]` on a
`<pre class="wn-ascii">` comes out a few pixels wide. `.wn-ascii` therefore sets
`width: max-content` and art is never given an explicit width.

### Rules and frames

**`<hr>` is banned.** Horizontal rules are box-drawing characters in a real text node, so
they inherit the grid and the font:

```
─  U+2500  default rule
═  U+2550  emphasised rule (section boundaries)
│  U+2502  vertical rule
┌ ┐ └ ┘    frame corners
├ ┤ ┬ ┴ ┼  frame joins
╲  U+2572  the mark's left wall
╱  U+2571  the mark's right wall; hatching, "unknown / indeterminate" fill
░ ▒ ▓ █    shading and ASCII art
```

Frames are drawn by `components/AsciiPanel.tsx`. It renders the corner and edge
characters as text and lets the browser repeat the horizontal run, so a frame is always an
integer number of columns wide. Do not fake a frame with `border: 1px solid` — the whole
point is that the frame is *made of characters*.

Rules are `--color-line-strong` for section boundaries and `--color-fg-faint` for
everything inside a panel.

---

## 4. ASCII art

The hero wordmark and the mark are **real character output**, never an image and never
text baked into an SVG.

- Art lives in `lib/ascii.ts` as arrays of equal-length rows. `toArt()` pads every row to
  the width of the widest and reports that width. Ragged rows are a bug; padding means a
  ragged row degrades to trailing spaces rather than to a collapsed grid.
- Rendered in a `<pre>` with `aria-hidden="true"`. **A visually-hidden real heading always
  carries the accessible name** — screen readers get `<h1>winnow</h1>`, not 470 block
  characters.
- Sizing is computed, not guessed. The wrapper sets `container-type: inline-size` and the
  `<pre>` gets `font-size: min(<cap>, 100cqw / (<cols> × 0.6))`, with `<cols>` passed in as
  a CSS variable by the component. That is why the 0.6em advance matters: the art fits its
  container exactly at any viewport, with no breakpoints and no second smaller copy.
- `white-space: pre`, no wrapping, ever. A wrapped piece of ASCII art is worse than no art.

### Where the mark came from

**It was invented here.** There is no winnow icon, no SVG and no brand colour anywhere in
`Xapicc/winnow`; the letterforms and the mark in `lib/ascii.ts` were drawn for this site
against the grid. A later run looking for the product asset these were transcribed from
will not find one, because there is not one. This paragraph exists so that nobody spends a
work cycle looking.

**The mark is a funnel:** eleven columns of intake, converging walls in `╲` and `╱`, three
columns of spout. That is the tool in one shape — more goes in than comes out.

Two things about it were decided by looking at a render rather than by reasoning, and both
are recorded because the reasoning went the other way first:

- **The funnel is an outline, not a fill.** The first draft filled the 11 × 5 block, `█`
  for what is kept and `░` for what is shed, tapering 11 → 3. At hero size the stipple read
  as noise rather than as chaff, and the filled block was a slab of accent that spent §1's
  whole one-element budget before the wordmark started.
- **`W` is seven columns where every other letter is six.** At six it has to fit two outer
  strokes, two valleys and a centre riser into four interior columns, and every version
  that does reads as `H` — `WINNOW` came out as `HINNOH` on the first build. Uniform letter
  widths are not a rule here; `word()` joins whatever width each glyph is.

**The composition is the mark above the word, one blank row between: 43 × 11.** The word
sets the width, the mark is centred on it, and the spout lands on the middle of the word.
That is the reason for this lockup rather than a mark beside the word — it reads as one
object because the word is what falls out of the funnel. Keep that relationship.

`app/icon.svg` is the one place the mark is not character output, because a browser tab
cannot render a `<pre>`. It is the same three parts at 32 × 32. If the mark changes, that
file changes with it.

---

## 5. Motion

The site has **one** hero effect and it is the decode.

- **Decode-in.** On load, the wordmark resolves from noise: each non-space cell shows
  random glyphs from `░▒▓█▚▞#%*+=-` and settles to its target, staggered left-to-right and
  top-to-bottom. Total 900 ms, one pass, never repeats, never replays on scroll.
- The server renders the **resolved** art. The scramble is installed in a layout effect
  before first paint, so there is no flash of resolved-then-broken text, and a client with
  no JavaScript sees the finished wordmark.
- No per-character luminance wave. It was the alternative, not an addition — pick one, and
  the decode is picked.
- The decode is the one thing on the site that draws the eye, so it is not allowed to do it
  where nobody is looking. `lib/motion.ts` tests the element's box against the viewport
  **synchronously, before first paint** — an `IntersectionObserver` cannot answer that in
  time and starting after it would be the flash this section forbids — and an observer plus
  a `visibilitychange` listener then *settle* it to resolved text if it leaves the viewport
  or the tab is backgrounded mid-run. Settling, never pausing: a half-decoded wordmark is
  not a state anyone should return to.

**The frame itself is pure.** `lib/decode.ts` computes one frame from the art, the
progress and a churn counter, with no clock and no DOM, so it can be checked without a
browser. `lib/motion.ts` owns the clock, the viewport test and the teardown and nothing
else. This is a deliberate departure from the reference, which carries the same arithmetic
in both files and has to keep them in step by hand.

Everything else is a state change, not an animation:

```
--motion-fast : 120ms   hover, focus ring
--motion-base : 180ms   colour and border transitions
--motion-slow : 240ms   the largest thing that may move
```

All of it lives in one block on `:root` in `app/globals.css`, including the three that time
the decode itself — `--motion-decode`, `--motion-decode-churn`, `--motion-decode-stagger`.
`lib/motion.ts` reads all three from the computed style at run time and **throws if one is
missing** rather than falling back, so a deleted token is a loud failure in the check run
instead of a quiet change of feel. The stagger is passed *into* `lib/decode.ts` rather than
read from its constant, so the CSS stays the single source of truth for the one effect. No
component carries a duration of its own.

Easing is `cubic-bezier(0.2, 0, 0, 1)` throughout, declared as `--ease-grid`. Nothing on
this site loops, pulses, blinks, marquees or attracts attention after the first second.
There is no scroll-jacking and no parallax.

**Colour state changes go through `.wn-state`, and Tailwind's `transition-colors` is not
used anywhere.** Its property list includes `outline-color`, so the focus ring interpolates
from the element's own colour — on the filled button that is near-black, and the ring is
invisible for 150 ms at exactly the moment it is needed. The ring is a state, not an
animation.

### Reduced motion — the contract

Under `@media (prefers-reduced-motion: reduce)`:

- The wordmark renders **statically resolved, with no animation at all.** Not a faster
  decode, not a fade: the component reads `matchMedia("(prefers-reduced-motion: reduce)")`
  and never enters the animation path — no timer is scheduled and no frame is requested.
- All transitions collapse to `0.01ms` via a global rule in `app/globals.css`.
- Any future effect must be written the same way: check the query *before* scheduling
  work, not by animating and hoping the media query hides it.

---

## 6. Texture

Four textures, all of them close to subliminal. Measured in `app/globals.css`; if you can
see one clearly in a screenshot at 100%, it is turned up too far.

1. **Scanlines** — a fixed full-page overlay, `repeating-linear-gradient` of a 1px line
   every 3px, `rgba(255,255,255,0.014)`, `pointer-events: none`, `z-index: 60`.
2. **Grid** — a fixed overlay of vertical and horizontal lines on a `72px` cell in
   `rgba(255,255,255,0.02)`, masked with a radial gradient so it fades out below the fold
   and never competes with body copy.
3. **Phosphor glow** — accent text may carry
   `text-shadow: 0 0 18px color-mix(in oklab, var(--color-accent) 28%, transparent)`.
   Only on the ASCII art and the wordmark. Never on body copy, and **not on the filled
   button**: its label is canvas-dark on a saturated fill, so the glow paints an orange halo
   *behind* dark glyphs and reads as a rendering fault rather than as texture.
4. **Chromatic aberration** — on **hover** of an interactive element only, never on focus:
   two 0.4px text-shadows, one red at −0.4px and one blue at +0.4px, both at very low
   alpha, over `--motion-fast`. It should read as a slight instability, not as a 3D effect.
   It is disabled under reduced motion.

**The aberration pair stays red/blue under an orange brand.** It is a lens artefact, not a
brand mark. Fringing in the accent's own hue would read as a glow on accent text and as
nothing at all on the grey text where the effect actually has to be visible, so the pair is
picked for separation from the accent rather than from it.

Two limits on 3 and 4, both learned by looking at a screenshot:

- **One hover effect per target.** Where a control already answers a hover with a fill and
  a colour change — the section rows on the home page — the fringe is a third thing
  happening on one element and it is cut, not added to.
- **The fringe never runs on the same element as the focus ring.** The ring is the signal;
  a colour fringe on the one element that has to stay legible competes with it. Focus gets
  the outline and nothing else.

Never: CRT barrel distortion, vignettes, flicker, noise that animates, glitch-jitter on
text that people have to read.

---

## 7. Components

The primitives in `components/` are the vocabulary. Extend them; do not invent parallel
ones.

- `AsciiPanel` — a box-drawing frame with an optional label welded into the top edge
  (`┌─ label ─────┐`). The frame is characters. **Labels are one or two words**: the label
  cannot shrink without clipping, and a long one pushes the frame off a narrow screen.
  Two rules the frame depends on, both easy to break by accident: every fixed piece of the
  edge is `shrink-0` (a shrunk flex item with `white-space: pre` overflows *visibly*, and
  the overflow strikes through the label), and the vertical edges are absolutely
  positioned (`overflow: hidden` clips their paint but would not stop 200 rows of `│`
  from setting the panel's height).
- `SectionHeading` — kicker, heading, and a `═` rule that fills the remaining width.
- `TerminalBlock` — an inset well for commands and output. A `$` prompt is rendered as a
  non-selectable `::before` so copying the block copies only the command.
- `Button` — `variant="primary"` is filled `--color-accent` with `--color-canvas` text;
  `variant="ghost"` is a `[ bracketed ]` label in the accent on hover. Both are `2.25rem`
  tall.
- `Ascii` / `DecodeAscii` — fixed and decoding character art, both `aria-hidden`.
- `AsciiRule` — a `─` or `═` run that fills the width it is given.
- `Ticks` — renders `` `backticked` `` spans in a plain string as accent-coloured code.
  Because the whole site is monospace, a code span cannot be marked by family — colour is
  the only signal available, and body copy is the one place the accent is allowed to appear
  for that reason.
- `SpecList` — a term and its meaning, two columns where there is room.
- `AsciiFigure` / `ScriptedFigure` / `useScriptedSteps` — the figure vocabulary. **These
  three ship unused.** They are here because the figures a later run draws belong in them
  rather than in something invented on the spot, and because `ScriptedFigure` is where the
  reduced-motion and off-screen rules of §5 are already enforced. A figure written any
  other way has to re-argue both.

Focus is always visible: `outline: 2px solid var(--color-accent)` with a `2px` offset. Do
not remove it, do not replace it with a colour change alone, and **do not transition it** —
see §5 on `.wn-state`.

Every interactive element is at least `24×24` (WCAG 2.5.8). A `--text-small` link is a
20px line box, which is under it, so the links in the header and footer carry `min-h-6` and
an `inline-flex` to make the box real rather than nominal.

The header drops its `source ↗` link below `640px`; four items do not fit a 390px row, and
the same link is in the hero and in the footer. **There is deliberately no mobile
disclosure menu.** Three items fit a 320px row with the brand, so a hamburger would hide
two links behind a control, cost a focus trap and an Escape handler, and buy nothing. If
the nav ever grows a fourth item, that is the moment to revisit it — not before.

Routes come from `NAV_LINKS` in `lib/site.ts`, and `ROUTES` is derived from it rather than
listed twice: a page nothing links to is a page that does not belong in the sitemap either.
Deep links carried by a section's ghost button live on that section's entry in `SECTIONS`,
so adding a section and forgetting its anchor is one edit rather than two.

---

## 8. Copy

The voice is the project's own: technical, plain, specific, and willing to state a limit.
Read `README.md`, `docs/SPEC.md`, `docs/COZEMPIC.md` and `docs/USAGEFOUNDRY.md` in
`Xapicc/winnow` before writing anything. Its register, verbatim: *"No claim that pruning a
Claude Code session saves money has been made, by anyone."*

- Name the mechanism. "Placed after the last `cache_control` breakpoint" beats "optimises
  your context".
- Lower case for nav, kickers and labels; sentence case for headings. No Title Case.
- Prefer a real path, flag, endpoint or unit over an adjective.
- State a caveat where the project states one. It is careful about which of its numbers are
  measured, which are modelled and which are simulated; a site that flattens those three
  into "results" is lying on its behalf.

### Anti-cringe list — hard rules

1. **No emoji.** Anywhere. Not in copy, not in headings, not in the README of this
   directory. No rocket ships, no sparkles, no ✅.
2. **No Matrix katakana rain.** No falling glyph columns of any alphabet.
3. **No fake terminal that types filler forever.** If a terminal block shows a command, it
   is a command you can actually run.
4. **Banned words:** "AI-powered", "revolutionary", "supercharge", "10x", "unleash",
   "seamless", "game-changing", "effortless", "magic", "blazing fast", "next-generation",
   "empower".
5. **No fake social proof.** No logo wall, no testimonials, no star counts, no user
   numbers, no "trusted by".
6. **No invented numbers.** Every figure on the site must be traceable to `Xapicc/winnow`'s
   own documents. If the source does not state it, it does not go on the site.
7. **No pricing.**
8. **No claim the software does not make.**
9. **Effects honour `prefers-reduced-motion: reduce`,** by the contract in §5.
10. **No stock photography, no 3D renders, no gradient blobs, no glassmorphism.**

### winnow's own rules

11. **The pruner does not exist yet, and the site never implies that it does.** There is no
    `winnow fork`, no `winnow recover` and no `winnow bench`. Copy may describe what a
    pruner *would* cost, because that arithmetic is the project; it may not describe a
    pruner as a thing you can run. Present tense is reserved for `winnow inspect`,
    `winnow filter`, `winnow savings` and orchestrator-safe mode.
12. **Say which kind of number it is.** Measured, modelled, or simulated. The filter's
    8.21% is a replay over 175 historical sessions — what it *would* have done — and the
    site says so on the same line. "The figure is modelled, not billed" is the project's own
    phrasing and it is not decoration.
13. **A figure's caption never says the figure is live.** Every one of them is an
    illustration drawn from a fixed script, and several illustrate software that does not
    exist. `AsciiFigure` puts the caption in a real `<figcaption>` for this reason.
14. **Where the sources disagree, name the disagreement rather than picking quietly.** The
    project's own README does this in two places today: its Status table still lists
    milestone 1 as *not started* while the note at the top of the same file reports the
    number that milestone produced, and `src/winnow/inspect.py` is in the "what is here"
    table with 54 tests. The site follows the specific statement over the summary row, and
    `app/status/page.tsx` carries a comment saying so. A later run that finds this
    reconciled upstream should delete the comment, not the care.

---

## 9. Checking the work

`npm run typecheck` and `npm run build` both pass on a clean checkout with no `.env`, and
every route prerenders static. That is the whole of what is checked today.

**The test layer is not written yet.** `npm test` and `npm run test:e2e` are wired —
`vitest.config.mts` and `playwright.config.ts` are configured, the latter pointing at an
`e2e/` directory a later run creates — but the only test in the tree is
`lib/ascii.test.ts`, which asserts the geometry of art that was invented in this repository
and is therefore not checkable against anything upstream. A later run writes the rest. What
it has to cover, from the claims made above that markup alone cannot prove:

- the hero scrambles and then resolves, and the reduced-motion path never enters the
  animation (§5)
- the art is `aria-hidden` behind a real `<h1>` (§4)
- the first tab stop is a visible skip link (§7)
- no internal link or in-page anchor is dead (§7) — every `SECTIONS[].href` resolves to a
  heading that exists
- nothing overflows sideways at six widths (§3)
- axe finds no serious or critical violation on any route at either width
- the filled button is canvas-on-accent and never white-on-accent (§1)
- every character in `lib/ascii.ts` is inside the shipped font subset, read out of the
  font's own `cmap` (§2)

Two of those are written the way they are because the eye is bad at them, and whatever
implements them should inherit the reasoning. A contrast check composites through ancestors
rather than reading a class name, because a token that measures 3.92:1 looks fine on a good
monitor. A focus-ring check samples with no settling time, because the failure it catches is
a 150 ms fade, not an absence.

**A change to a rule in this file is not finished until the checks that cover it pass
against it**; if a rule here stops being checkable, say so here rather than deleting the
check. The rules with no check today, and why: §1's measured contrast ratios (axe
re-measures the rendered result, which is the claim that matters), §4's two
decided-by-looking rules, which are a judgement about a render and not an assertion, and
§8's copy rules, which need a person.
