# Docs style guide

The bar is Stripe / Ramp / Kalshi. A reader should be able to scan a page, copy a working request,
and understand the contract without wading through prose.

Assume every reader is one of three people, often all three at once:

- **Hostile.** They will find the contradiction, the stale number, the broken sentence. Anything
  stated twice will eventually be stated two different ways, and they will screenshot it.
- **Unfamiliar.** Overexplain rather than underexplain. Define the term the first time it appears,
  or link to where it is defined.
- **Busy.** They will read the table and skip the paragraph. Put the answer in the table.

## Hard rules

These are not preferences. A page violating one of these is wrong.

### No em dashes

Never use `—`. Not once, not "sparingly". Replace it with one of:

| Instead of | Use |
| --- | --- |
| Two independent clauses joined by `—` | A full stop. Two sentences. |
| An aside `—like this—` | Parentheses, or cut the aside. |
| A definition `term — meaning` | A colon, or a two-column table. |
| A trailing afterthought | Cut it or promote it to its own sentence. |

En dashes (`–`) are banned too, including in numeric ranges. Write `2 to 5 legs`, or
`2-5 legs` with an ASCII hyphen. Hyphens in compound words are fine.

Inside backticks, formulae are **ASCII only**: `a * b`, `a - b`. Never the Unicode `×` or `−`.
Unicode math characters have already caused one mojibake incident in this repo.

### No writing about the writing

The reader is here for the product, not for a tour of the documentation. Delete any sentence that
describes what the page is doing.

Banned openers and constructions:

- "This page maps / covers / walks through..."
- "...gathered in one place", "...you'd otherwise piece together from"
- "Knowing this up front makes the table below scannable", "at a glance"
- "worth knowing", "the ones worth knowing", "a few things worth knowing"
- "Note that", "It's worth noting", "Keep in mind"
- Rhetorical questions: "Not sure which channel fits?", "Need the full map?"
- Editorialising about the reader: "Serious integrations often run both."

Say the thing. If a table needs a preamble to be scannable, fix the table.

### Every number has exactly one home

Limits, fees, ranges, timeouts, and rate limits live on [Limits and fees](/guides/limits-and-fees).
Error codes live on [Errors](/api-reference/errors). Term definitions live on
[Glossary](/guides/glossary).

Every other page **links** to those. It does not restate them. A fee quoted on four pages becomes
four different fees the first time it changes.

### Document the contract, not the internals

Describe what the integrator observes: endpoints, statuses, fields, behavior, guarantees. Do not
name internal services, internal algorithms, or reconciler mechanics. If a mechanism is not
something the reader calls, sees in a response, or must handle, leave it out.

Transparency means the reader can predict what the API will do. It does not mean a tour of the
backend.

## Voice

- **Second person, present tense.** "You send", "you receive". Never "the user sends" or "the
  frontend creates".
- **Lead with the task.** The first sentence of a section says what you do or get, not background.
- **One idea per sentence.** If a sentence has two clauses and a parenthetical, it is three
  sentences.
- **No marketing filler.** No "Welcome to", "We're excited", "powerful", "seamless", "robust".
- **Bold carries weight only if it is rare.** Bold a term on first definition, or a value in a
  table. Do not bold mid-sentence for emphasis. A page with fifteen bolded fragments has none.

## Formatting

- **Sentence case for every title and heading**, including API reference pages. "Get your API key",
  not "Get Your API Key". "Confirm quote", not "Confirm Quote". Only proper nouns are capitalized.
- **Single quotes in frontmatter**, consistently.
- **One term per concept.** A *parlay* is the product. An *RFQ* is the API object that represents
  one after commit. A *quote request* is the pre-trade price-discovery object. A *position* is the
  on-chain, funded parlay. Pick the right term for the layer and do not swap mid-page. See
  [Glossary](/guides/glossary).
- **Code is copy-paste-first.** Show a real `curl` with the auth header, real-ish values, and the
  response shape. Prefer a runnable example over a prose description of one.
- **Use current paths in examples.** The supported contract surface is `/v1/...`. Public
  unauthenticated reads keep their own roots (`/markets`). Never use the deprecated flat
  `/user` / `/rfqs` roots.

## Pictures

- **Concept pictures, not diagrams.** Each core concept page opens with one picture that a
  non-technical reader can follow: at most four columns, plain words, one highlighted object, no
  status names, field names or units. Those belong in the tables below the picture.
- **PNG pairs.** `images/pictures/<name>-light.png` and `<name>-dark.png`, 1540 by 952, embedded as

  ```jsx
  <img className="block dark:hidden rounded-2xl" src="/images/pictures/<name>-light.png" alt="what it shows" />
  <img className="hidden dark:block rounded-2xl" src="/images/pictures/<name>-dark.png" alt="what it shows" />
  ```

- **One source, rendered.** Words and layout live in `images/pictures/src/build.py`; the look lives
  in `images/pictures/src/pics.css`. Change the words, run `python build.py` there, then
  `cd scripts && npm install && node render-pictures.mjs` to re-render both themes. Commit the
  source and the PNGs together.
- **The visual language.** A betting slip with venue marks for the parlay. Competing odds tags for
  makers. Node and rail connectors. A lifecycle rail under the picture. One accent border and a soft
  glow on the object the page is about. DM Sans and DM Mono. No avatars, no icons, no arrows.
- **Screenshots for anything with a screen.** Where the app has the UI, show the app, not a picture.
  Blur balances, addresses and key material. Never show the BYOW preset.
- **Never inline SVG.** Mintlify strips `text`, `circle`, `marker` and `title` from inline SVG, so it
  renders as empty boxes.

## Structure

- **Get started** (Introduction, Quickstart, Authentication). A new reader reaches a working call in
  minutes.
- **Core concepts** (how parlays work, vaults and funding, limits and fees, glossary). The mental
  models.
- **Guides** (reading your data, webhooks, real time, market making). Task-oriented how-tos.
- **API reference.** One page per operation, generated from the OpenAPI spec where possible.

A page belongs in exactly one place. Concepts explain *what and why*. Guides explain *how*. The
reference is the *exact* surface.

## BYOW / partner surface

The headless / sub-account (BYOW) surface and the partner narrative stay gated under `_internal/`.
Public guides are principal-scoped. Never document `X-Subaccount` or sub-account variants in the
public tree.

## Before you merge

```bash
# no em or en dashes, and no Unicode math, anywhere public
# (openapi.json descriptions render into the docs, so it is checked too)
LC_ALL=C.UTF-8 grep -rn -e "—" -e "–" -e "−" -e "×" -e "…" -e "→" \
  --include=*.mdx --include=openapi.json . | grep -v "^./_internal/"

# no hardcoded colors in pages, and every picture ships as a light and dark pair
grep -rn "#[0-9a-fA-F]\{6\}" --include=*.mdx .
ls images/pictures/*-light.png | sed 's/-light//' | while read f; do test -f "${f%.png}-dark.png" || echo "missing dark: $f"; done

# no Title Case reference titles
grep -rn "^title:.*[a-z] [A-Z]" --include=*.mdx api-reference/ \
  | grep -vE "API|P&L"
```

All three must return nothing.
