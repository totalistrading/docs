# Docs style guide

The bar is Stripe / Ramp / Kalshi: a reader should be able to scan a page, copy a working
request, and understand the contract without wading through prose. Keep these rules.

## Voice

- **Second person, present tense.** "You send", "you receive" — not "the user sends" or "the
  frontend creates". Address the reader, never describe a third party.
- **Lead with the task.** First sentence of a section says what you do or get, not background.
- **Short sentences.** One idea each. Break run-ons. Use em dashes sparingly — at most one per
  sentence.
- **Document the contract, not the internals.** Describe what the integrator observes: endpoints,
  statuses, fields, behavior, guarantees. Do not name internal services (`vault-job-service`,
  `vault-settlement-service`), internal algorithms (ILP), or reconciler mechanics. If a mechanism
  isn't something the reader calls, sees in a response, or must handle, leave it out.
- **No marketing filler.** No "Welcome to", "We're excited", "powerful", "seamless". State what the
  thing is and how to use it.

## Formatting

- **Headings are sentence case.** "Get your API key", not "Get Your API Key". Only the page title
  (frontmatter) and proper nouns are capitalized.
- **One term per concept.** A *parlay* is the product. An *RFQ* is the API object that represents
  one. A *quote request* is the pre-trade price-discovery object. A *position* is the on-chain,
  funded parlay. Pick the right term for the layer and don't swap mid-page.
- **Code is copy-paste-first.** Show a real `curl` (or fenced HTTP) with the auth header, real-ish
  values, and the response shape. Prefer a runnable example over a prose description of one.
- **Use current paths in examples.** The supported contract surface is `/v1/...`; the public
  unauthenticated reads keep their own roots (`/markets`, `/leaderboard`). Never use the deprecated
  flat `/user`/`/rfqs` roots.

## Structure (information architecture)

- **Get started** — Introduction, Quickstart, Authentication. A new reader should reach a working
  call from here in minutes.
- **Core concepts** — the mental models: how parlays work, vaults & funding, settlement & cashout.
- **Guides** — task-oriented how-tos: reading your data, webhooks, real-time, market making.
- **API reference** — generated from the OpenAPI spec; one page per operation.

A page belongs in exactly one place. Concepts explain *why/what*; guides explain *how*; the
reference is the *exact* surface.

## BYOW / partner surface

The headless / sub-account (BYOW) surface and the partner narrative stay gated under `_internal/`.
Public guides are principal-scoped; never document `X-Subaccount` or sub-account variants in the
public tree.
