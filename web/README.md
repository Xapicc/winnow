# winnow — the site

The marketing site for [winnow](https://github.com/Xapicc/winnow). Next.js 15 (App
Router), React 19, Tailwind v4, TypeScript. Three runtime dependencies: `next`, `react`,
`react-dom`. No CMS, no analytics, no runtime font CDN, no environment variable required
to build or serve.

Four static routes — `/`, `/arithmetic`, `/filter`, `/status` — plus a 404, an icon, a
share card, `robots.txt` and `sitemap.xml`. Every one of them prerenders.

## The design contract

**[`docs/design-language.md`](docs/design-language.md) is the contract, and it is the only
one.** Palette, type scale, the character grid, the art, motion, texture, the component
vocabulary and the copy rules all live there, with the measurement or the render that
decided each one. If a rule is not in that file it is not a rule; if a rule in it is wrong,
it gets changed there first and in the code second.

Section 9 of that file lists every check in this directory and what each one asserts,
including the three rules that will never have one.

## Running it

Node 22 or later.

```
npm install
npm run dev          # http://localhost:8010
```

`npm run build && npm start -- --port 4322` serves the production build, which is what the
browser-based checks run against — never the dev server, which serves different markup,
different assets and an error overlay.

## The scripts

| Script | What it does |
|---|---|
| `npm run dev` | Dev server on 8010. |
| `npm run build` | Production build. Every route prerenders static; the share card is rasterised here. |
| `npm start` | Serves the build. `-- --port N` to move it. |
| `npm run typecheck` | `tsc --noEmit` over the app, the tests and the e2e suite. |
| `npm test` | Vitest. Art geometry, the font subset, the decode arithmetic, the payback formula, the copy marks, the component contracts, and every route rendered to static markup. No browser. |
| `npm run test:e2e` | Playwright against a production build it starts itself, on port 4322. Motion, keyboard, layout at six widths, axe on every route at two widths, links, and what a host has to serve. |
| `npm run check` | Behavioural checks against a serving instance, reporting the numbers rather than pass/fail: the measured contrast table, every text node's ratio, every tab stop's ring and target size. |
| `npm run shoot` | The screenshot set in `docs/screenshots/`, plus an overflow probe at every width. |

`check` and `shoot` do not start a server. Point them at one:

```
npm run build
npm start -- --port 4322 &
npm run check -- http://127.0.0.1:4322
npm run shoot -- http://127.0.0.1:4322
```

`test:e2e` needs a browser binary. If `npx playwright test` reports a missing executable:

```
npx playwright install --with-deps chromium
```

## What is checked, and what is not

`npm test` and `npm run test:e2e` are the gate; `npm run check` is the readout. Between
them they cover the contrast floor, the reduced-motion contract, the focus ring, the
character grid at 320px through 1920px, the accessibility surface, and every link and
anchor on the site.

They do not cover the copy. Whether a sentence names its mechanism, says whether a number
is measured, modelled or simulated, or claims something the software does not do needs a
reader — see section 8 of the design language, and the note at the end of section 9 for the
rest of what a person still has to look at.

## Deploying

Any host that runs a Next.js App Router build: `npm ci && npm run build`, then
`npm start`. Vercel needs no configuration beyond pointing it at this directory. There is
no server-side state, no database and no secret.

One variable, and it is optional:

- `NEXT_PUBLIC_SITE_URL` — the canonical origin, used for `metadataBase`, the sitemap and
  `robots.txt`. It defaults to the value committed in `lib/site.ts`, so a clean clone with
  no `.env` still emits correct absolute URLs. Set it when the site gets a domain, and
  change the default in the same commit.

The site is not deployed anywhere yet.
