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
  for box-drawing frames, grid lines, ASCII filler and disabled glyphs — shapes, not
  words. If a sentence, a name or a numeral has to be read, it is at least
  `--color-fg-muted`. The rule is easy to break by eye, because 3.92:1 looks like a
  tasteful grey on a good monitor.

  **`aria-hidden` is not a licence, and this paragraph used to say it was.** It listed the
  `01`–`06` ordinals on the home page as a permitted use because they duplicate a visual
  order and are not announced. That was wrong in the way §9 warns about: not being
  announced says nothing about being legible, and a sighted reader reads `01` at 3.92:1
  whatever the accessibility tree thinks. `e2e/a11y.spec.ts` measures the rendered result
  and reported seven serious `color-contrast` nodes on the home page for exactly this. The
  ordinals are `--color-fg-muted`, and so are the two labels in `FilterPositionDemo` that
  said which rule fired and what happened to the request. Every remaining use of the token
  is a shape: frames, rules, the bracket glyphs on a ghost button, the unfilled remainder
  of a bar.
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

**A bar is a decoration; the number beside it is the fact.** `PaybackDemo` was ported with
its whole 18-cell bar drawn in the verdict's tone, and four rows of it put two saturated
slabs of green and two of red on one figure — the hacker theme this document opens by
forbidding, arrived at one honest step at a time. The rule that came out of looking at it:
in a figure, the tone goes on the value and on any glyph that changes meaning (`▸` for "off
the end of the axis"), and the bar is drawn in `--color-fg-muted` against a `--color-fg-faint`
remainder. Filled and empty still differ in glyph, so the reading survives greyscale either
way. The same edit applies to `FilterPositionDemo`, whose accent is spent on the `→ pointer`
marks rather than on the twenty cells of cached prefix beside them.

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
- **286 code points, and the list is now read out of the file rather than described.**
  `lib/font.test.tsx` parses the WOFF2 container, brotli-decompresses it, walks the `cmap`
  and fails on any character the site renders that the font does not carry. It found two on
  the run that wrote it, both in body copy: **`§` U+00A7 and `±` U+00B1 are not in the
  subset.** Write "section 4" and "3 points either way" until somebody re-cuts the font;
  neither one can be re-cut from inside the harness container, which has no `fontTools` and
  no network. Also outside it and worth knowing before reaching for one: `«»`, `‰`, `†`,
  `≈`, `≤`, `≥`, `∞` and every emoji. Inside it and easy to miss: `▸` U+25B8, `●`, `■`, `▲`,
  `○`, `□`, `▪`, `−` U+2212, `×`, `·`, `—`, `–`, `…`, `°`, `©`, and the four arrows
  `←↑→↓` plus `↗`.
- **Every glyph in the file has advance width 600/1000 = `0.6em`.** All character-grid
  arithmetic on this site depends on that constant.
- No italics. The italic face is not shipped; use weight or colour for emphasis instead of
  letting the browser synthesise an oblique.

**The OpenGraph card is the one surface that is not set in this font, and it could not
be.** `app/opengraph-image.tsx` draws the card at build time, and Satori rejects the
`wOF2` signature outright — it cannot read the subset this site ships, and the face it
falls back to has no `█` to draw with, let alone the `╲` and `╱` the mark's walls are
made of. So the wordmark on the card is **SVG geometry on the same 0.6 grid**: one
rectangle per horizontal run of `█`, one line per diagonal cell, at final pixel
coordinates because Satori rasterises an SVG child at its declared size and does not
scale a viewBox to fit. Successive `╲` cells step one column right and one row down and a
cell is one column by one row, so the diagonals chain into a continuous wall with no join
to draw.

The two text lines on the card are therefore in the renderer's bundled sans. The
alternative was a second, static copy of JetBrains Mono — a TTF decompressed from our
WOFF2 is still a *variable* font, which Satori cannot instance — and ~90 kB in the
repository for one image is not worth it. **Do not fix this by committing a second font
instance.** The Twitter card is `summary_large_image` since the card exists; it was
`summary` before, because a large-image card with no image is a broken card, and the two
move together.

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
- `Ticks` — renders the two marks the copy is written with. `` `backticked` `` spans become
  accent-coloured code: the whole site is monospace, so a code span cannot be marked by
  family, colour is the only signal available, and body copy is the one place the accent is
  allowed to appear for that reason. `*starred*` spans become emphasis in **weight and tone,
  never slope** — there is no italic face in the subset, so an `<em>` left alone would be a
  synthesised oblique. The star mark exists because the copy is lifted out of markdown
  documents that use it, and an unhandled `*word*` renders as two pieces of punctuation that
  look like markdown nobody compiled. Backticks resolve first, so a star inside a code span
  stays literal. **`**double**` is not a mark**, and a page carrying an odd star fails
  `app/routes.test.tsx` rather than quietly swallowing the rest of its sentence.
- `SpecList` — a term and its meaning, two columns where there is room.
- `ComparisonTable` — a real `<table>`, for the one set of real numbers on the site that is
  shaped like one. **It is deliberately not a figure.** Rule 13 below makes every figure an
  illustration and hides its drawing from screen readers; the intake filter's replay is a
  measurement, and a measurement a screen reader cannot read is not a measurement it has
  been told. Its `<caption>` sits below the rows and is the only place the source is named.
- `AsciiFigure` / `ScriptedFigure` / `useScriptedSteps` — the figure vocabulary, and the
  four figures in `components/demos/` are written in it. `ScriptedFigure` is where the
  reduced-motion and off-screen rules of §5 are enforced, so a figure written any other way
  has to re-argue both.

Focus is always visible: `outline: 2px solid var(--color-accent)` with a `2px` offset. Do
not remove it, do not replace it with a colour change alone, and **do not transition it** —
see §5 on `.wn-state`.

Every interactive element is at least `24×24` (WCAG 2.5.8). A `--text-small` link is a
20px line box, which is under it, so the links in the header and footer carry `min-h-6` and
an `inline-flex` to make the box real rather than nominal.

The header drops its `source ↗` link below `640px`; four items do not fit a 390px row, and
the same link is in the hero and in the footer. **There is deliberately no mobile
disclosure menu.** Three items fit a 320px row with the brand, so a hamburger would hide
two links behind a control, cost a focus trap and an Escape handler, and buy nothing.

**The fourth item arrived, and the answer is still no.** `/filter` made four, which this
section said was the moment to revisit. Revisited: `source ↗` is already gone below `640px`,
so a phone still carries three links, and three fit 320px **once each label loses its
article** — "the arithmetic" and "the filter" became `arithmetic` and `filter`, and the row's
gap tightens from `2ch` to `1.5ch` below `sm`. Measured in a browser at 320px, not computed.
A fifth item is a different conversation, and the articles are already spent.

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

`npm run typecheck`, `npm test`, `npm run build` and `npm run test:e2e` all pass on a
clean checkout with no `.env`, and every route prerenders static. `npm run check` and
`npm run shoot` run against a serving instance; `web/README.md` has the invocations.

**The test layer is complete.** Nothing in this document is owed a check any more, and
the three rules that will never have one are named at the end of this section.

### Without a browser — `npm test`

- `lib/ascii.test.ts` — the geometry of art invented in this repository, so not checkable
  against anything upstream: every row of every piece is exactly `cols` wide, the lockup
  is 43 × 11, and the mark takes in more than it lets out.
- `lib/decode.test.ts` — the frame arithmetic (§5). The schedule, the invariant that
  `stagger + resolveWindow === 1`, that spaces never scramble so the block never changes
  shape, that resolution is monotonic, and that the three `--motion-decode-*` tokens in
  `app/globals.css` are the numbers these tests are written against — the CSS is the
  source of truth, so a token edited there and not here leaves the file asserting a decode
  the site does not run.
- `lib/payback.test.ts` — the break-even formula, ported with the code it tests. Every way
  of getting `19·(S/D) − 20` wrong typechecks, and all of them produce a smaller, friendlier
  number.
- `lib/font.test.tsx` — every character every route renders is in the shipped `cmap` (§2).
  Not "every character in `lib/ascii.ts`" as this list originally asked: the pages turned out
  to be where the misses were.
- `components/Ticks.test.tsx` — both copy marks, including that emphasis is upright.
- `components/components.test.tsx` — the contracts that live in components rather than in
  `lib/`: the filled button is `bg-accent` on `text-canvas` and never white (§1), it
  carries neither the glow nor the fringe (§6), neither variant uses `transition-colors`
  (§5), an external link gets `target="_blank"` *and* `rel="noopener"`, art hands its
  column count to CSS, and `DecodeAscii` renders the resolved art on the server.
- `app/routes.test.tsx` — every route renders, has exactly one `<h1>`, hides its character
  art behind it (§4), links only to routes in `ROUTES`, links only to anchors that exist on
  the page they name, and leaves no unresolved emphasis star (§7). Every `SECTIONS[].href` is
  resolved against the rendered markup of the page it points at.

### With one — `npm run test:e2e`, against `next build` and `next start`

Never the dev server: it serves different markup, different assets and an error overlay,
so a green dev run proves nothing about what a deployment would serve.

- `e2e/motion.spec.ts` — the hero scrambles and then resolves; it does not replay on
  scroll; under reduced motion it is resolved from the first frame, no element anywhere is
  mid-scramble, transitions collapse rather than merely running faster, and **no animation
  frame is requested at all** — §5 asks the component to check the query before scheduling
  work, and a component that requests a frame and then bails has already paid for a paint.
- `e2e/keyboard.spec.ts` — the first tab stop is a visible skip link with a ring, it moves
  focus into `#main`, the header follows in `NAV_LINKS` order, and at phone width every nav
  item is a plain link with nothing to trap focus in (§7).
- `e2e/layout.spec.ts` — nothing overflows sideways on any route at any of the six widths,
  the hero never wraps, and no paragraph is set wider than 72ch (§2).
- `e2e/a11y.spec.ts` — axe finds no serious or critical violation on any route, including
  the 404, at either width.
- `e2e/routes.spec.ts` — every route serves 200 with a clean console, carries the chrome,
  and has no dead internal link, in-page anchor or cross-page anchor; every external link
  is `https:` and opens with `noopener`.
- `e2e/deploy.spec.ts` — the share card is a real PNG and every page points at it as a
  large image, the icon serves, the sitemap lists exactly `ROUTES` and every entry answers
  200, `robots.txt` names the sitemap, the font comes from this origin, and no served page
  leaks a filesystem path.

### Reading the numbers — `npm run check`

Playwright reports pass or fail; this reports the measurement, so a regression is legible
without opening a trace. It re-measures §1's whole table off `:root` and fails if any
entry has drifted from the numbers printed above, walks every text node on every route,
and prints how many tab stops carried the ring and how many text nodes were below AA.

Two of its checks are written the way they are because the eye is bad at them, and
whatever edits them should inherit the reasoning:

- **The contrast walk composites through ancestors** rather than reading a class name — a
  string sits on the flattened stack of every semi-transparent background above it, and the
  header is `bg-canvas/92`. And it decides what counts as readable **from the content of
  the string, not from `aria-hidden`**: `/[\p{L}\p{N}]/u`. A run of `────` is a shape and
  WCAG exempts it; `01` is a numeral somebody reads. Both were sitting at 3.92:1 behind the
  same attribute, and only one of them was allowed to be.
- **The focus-ring check samples with no settling time**, because the failure it catches is
  a 150 ms fade rather than an absence. Tailwind's `transition-colors` includes
  `outline-color`, so a ring interpolates from the element's own colour — on the filled
  button that is near-black. Nothing but a zero-wait sample can tell that rule from a
  comment about it.

### The record — `npm run shoot`

`docs/screenshots/` is the shot set: the home page at all six widths, the subpages at 320
and 1920, the reduced-motion hero, the focus ring on the filled button, and the share card.
The script also probes every element's box at each width and names anything that overflows.

**The shots are reproducible, and that took work.** A scripted figure starts when it is
40% in view, and `fullPage: true` scrolls the document to stitch its capture — so each
figure began playing as the capture passed it and was photographed on whichever frame it
had reached. Two runs against an unchanged site produced two different
`filter-1920-full.png`. `shoot.mjs` now scrolls the whole page first to start every
figure, then polls until no figure's text has changed for 700 ms, then returns to the top.
Nothing on this site loops, so that always terminates, and it waits for the last figure
rather than for a duration guessed from the longest script. A shot that changes now means
the render changed.

### What has no check, and why

**A change to a rule in this file is not finished until the checks that cover it pass
against it**; if a rule here stops being checkable, say so here rather than deleting the
check. Three things are not checked, and none of them is an oversight:

- **§4's two decided-by-looking rules** — the funnel is an outline rather than a fill, and
  `W` is seven columns. Both are judgements about a render. A test could assert the current
  shape, but it would only restate the art, and it would fail the moment somebody
  deliberately redrew it, which is not what a failing test should mean.
- **§6's four textures.** Their values are asserted nowhere because the rule is "if you can
  see one clearly in a screenshot at 100%, it is turned up too far", and that is a person
  looking at `docs/screenshots/`. The one part that *is* checked is the negative: `npm run
  check` confirms focus adds no chromatic fringe, because §6 makes that a rule rather than a
  preference.
- **§8's copy rules.** Whether a sentence names its mechanism, says which kind of number it
  is, or claims something the software does not do needs a reader. Two mechanical corners
  are covered — `app/routes.test.tsx` fails a page carrying an odd emphasis star, and
  `lib/font.test.tsx` fails a character the shipped subset cannot draw — but the anti-cringe
  list and rules 11 to 14 are read, not run.

§1's measured ratios used to be on this list. They are not any more: `npm run check`
re-derives the whole table from `:root` and fails on any drift, and `e2e/a11y.spec.ts` has
axe re-measure the rendered result, which is the claim that actually matters.
