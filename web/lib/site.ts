/**
 * Facts about the site itself. Everything else lives with the page that uses it.
 *
 * Every figure below is traceable to this repository's own documents — the
 * README, `docs/SPEC.md`, `docs/COZEMPIC.md`, `docs/USAGEFOUNDRY.md` — and the
 * source is named beside it. Nothing here may be a number nobody wrote down.
 * See docs/design-language.md §8.
 */

export const SITE_NAME = "winnow";

export const SITE_TAGLINE =
  "An instrument for deciding whether pruning a Claude Code session is worth what it costs.";

export const SITE_DESCRIPTION =
  "Several tools will strip tool output from a Claude Code session. None of them can tell you whether stripping it saved you anything, because the conversation sits in the API's cached prefix at 0.1× and every edit forces a full-price rewrite of everything after the cut. winnow measures that trade before it makes it. The pruner does not exist yet.";

export const REPO_URL = "https://github.com/Xapicc/winnow";

/**
 * Canonical origin, used for `metadataBase`, the sitemap and the robots file —
 * three places that cannot take a relative URL. The default is committed, so a
 * clean clone with no `.env` builds correct absolute URLs with nothing set.
 *
 * The site is not deployed anywhere yet. Set `NEXT_PUBLIC_SITE_URL` to point one
 * deployment somewhere else, and change this line when it gets a domain.
 */
export const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL ?? "https://winnow-web.vercel.app";

/**
 * Nav targets. Every one of these resolves to a route in this repo — later runs
 * build them out, but none of them is a dead link today.
 */
export const NAV_LINKS = [
  { href: "/arithmetic", label: "arithmetic" },
  { href: "/filter", label: "filter" },
  { href: "/status", label: "status" },
] as const;

/**
 * Every route this site serves, in sitemap order. Derived from the nav rather
 * than listed twice: a page nothing links to is a page that does not belong in
 * the sitemap either. `app/sitemap.ts` reads this, so a new page is added to
 * `NAV_LINKS` and nowhere else.
 */
export const ROUTES = ["/", ...NAV_LINKS.map((link) => link.href)] as const;

/**
 * The six sections of the home page, in the order they appear.
 *
 * Some of them describe software that runs and some describe software that does
 * not, and the list says which is which rather than levelling them — see
 * docs/design-language.md §8, "the pruner does not exist yet".
 *
 * `href` is the deep link the section's ghost button carries. Every one of them
 * resolves to a heading that exists on the page it names; a later run that adds
 * a section adds the anchor at the same time or the link is dead.
 */
export const SECTIONS = [
  {
    id: "arithmetic",
    index: "01",
    title: "Removing context does not obviously save money",
    href: "/arithmetic#formula",
    hrefLabel: "the break-even formula",
    /* README "The question": cache reads at 0.1×, writes at 1.25× (five-minute)
       or 2× (one hour), prefix-ordered matching, and the break-even formula. */
    line: "Cache reads bill at 0.1× and writes at 1.25× or 2×, and matching is exact and prefix-ordered — so an edit invalidates everything after the cut. A prune pays `1.9·S − 2·D` once and earns `0.1·D` back on every later turn.",
    detail:
      "Break-even is `T* = 19·(S/D) − 20` further turns. The ratio decides, not the size of the session: cut half the suffix and it pays for itself in 18 turns; cut a tenth and it needs 170 more turns than the session has had.",
  },
  {
    id: "inspect",
    index: "02",
    title: "Measure a session before touching it",
    href: "/status#inspect",
    hrefLabel: "what inspect reports",
    /* README, "What is here today" and the note at the top. */
    line: "`winnow inspect` reads one session and prints the composition readout, the six guards, the cache position and `T*`. It writes nothing.",
    /* No `§` and no `±` in rendered copy: neither is in the shipped font
       subset, and a fallback glyph is a different advance width. Checked by
       `lib/font.test.tsx`; recorded in docs/design-language.md §2. */
    detail:
      "Milestone 1's number has been produced: tier CB strips 10.2% of message content pooled and 8.8% at the median, against the 22.6% / 21.6% section 6 of `docs/SPEC.md` recorded and the 3 points either way section 9 asked it to reproduce within. It misses, and it was built to be allowed to say so.",
  },
  {
    id: "filter",
    index: "03",
    title: "Never let the bytes into the cache",
    href: "/filter#position",
    hrefLabel: "where it acts",
    /* README, "The intake filter". */
    line: "`winnow filter` is a local pass-through proxy. A tool result a rule would strip goes out in full on the one request the model acts on it, placed after the last `cache_control` breakpoint so the API never writes it to cache, and is dropped on the next request.",
    detail:
      "There is no break-even term, because nothing is edited. On a replay over 175 historical sessions it reaches 8.21% and is worth +3.76% of the bill, against the tier-CB pruner's 10.17% and +3.27% — 1.1×, and positive in 175 sessions out of 175 rather than 97 of 168.",
  },
  {
    id: "savings",
    index: "04",
    title: "Price what the filter actually did",
    href: "/filter#savings",
    hrefLabel: "what the ledger holds",
    /* README, "That table is a simulation. `winnow savings` is the instrument." */
    line: "`winnow savings` reads `~/.winnow/filter.jsonl`, joins each line to the Claude Code transcript on `request_id` to recover the session and how many API turns followed, and prices it. The simulation is a corpus average; this is one install's ledger.",
    detail:
      "The filter is stateless, so it re-drops the same result on every later request that still carries it: a ledger of 1,283 removal events on one install holds 49 distinct results, and summing `bytes_dropped` over lines would report 27× what was removed. The figure is modelled, not billed, and the command says so in its own output.",
  },
  {
    id: "safe",
    index: "05",
    title: "Run the inherited tool without it killing the session",
    href: "/status#safe",
    hrefLabel: "the six guarantees",
    /* README, "Orchestrator-safe mode"; docs/USAGEFOUNDRY.md §8. */
    line: "The vendored tool assumes an interactive user: it can defer a prune until you quit, ask you to run `init`, and start a daemon that will `SIGKILL` a session it judges too large. Under an unattended harness the session that daemon would kill is the one the tool is running inside.",
    detail:
      "Orchestrator-safe mode is one switch and six guarantees, each held from outside the tree it wraps: no termination, no resume, no updater, no writes to `~/.claude`, no competing with the harness's own context and cost controls, and nothing written into the model's memory.",
  },
  {
    id: "unbuilt",
    index: "06",
    title: "What does not exist",
    href: "/status#unbuilt",
    hrefLabel: "the whole list",
    /* README, the note at the top and "Status". */
    line: "There is no `winnow fork`, no `winnow recover` and no `winnow bench`. The pruner does not exist yet — the instrument does.",
    detail:
      "No claim that pruning a Claude Code session saves money has been made, by anyone. If the first milestone comes back saying the cache is already warm at a typical resume, the kill criteria say to stop, and stopping then is the intended outcome rather than a failure of it.",
  },
] as const;
