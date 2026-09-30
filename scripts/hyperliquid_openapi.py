#!/usr/bin/env python3
"""Publish the Hyperliquid API reference: hyperliquid/openapi.json and its tab in docs.json.

The source is hip4-backend's public spec (tools/public_openapi.py), which already leaves out the
app-only routes. This script:

- files every operation under one resource (PAGES): Markets, RFQs, Quotes, Positions, Withdrawals,
  Account, Makers, Deployment, Streams. The resource becomes the operation's tag;
- titles every page with one pattern, verb + resource ("Create RFQ", "Accept quote"), replacing
  the spec's summary;
- gives every page a stable URL, /hyperliquid/api-reference/<resource>/<title>, and puts the SDK
  equivalent on the pages of the trading flow, or a recovery note on the recovery reads (x-mint);
- writes the API reference tab: the endpoints overview, then one group per resource.

A route the spec has and PAGES does not place, or the reverse, stops the script.

    python3 scripts/hyperliquid_openapi.py --backend ../hip4-backend   # regenerate from a checkout
    python3 scripts/hyperliquid_openapi.py --spec exported.json         # or from an exported spec
    python3 scripts/hyperliquid_openapi.py --check                      # exit 1 if either file is stale
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "hyperliquid/openapi.json"
DOCS = ROOT / "docs.json"
PRODUCT = "Hyperliquid"
TAB = "API reference"
OVERVIEW = "hyperliquid/endpoints"
METHODS = ("get", "put", "post", "delete", "patch")

# Each resource, its tag description, and its pages in nav order as (route, page title).
PAGES: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "Markets": (
        "HIP-4 markets: the catalog, one market with its sides, and price history. No API key needed.",
        [
            ("GET /v1/markets", "List markets"),
            ("GET /v1/markets/{outcome_id}", "Get market"),
            ("GET /v1/markets/{outcome_id}/history", "Get market history"),
        ],
    ),
    "RFQs": (
        "Requests for quote. A taker creates an entry RFQ for new legs and a stake; a cash-out RFQ is "
        "created on a position.",
        [
            ("POST /v1/rfqs", "Create RFQ"),
            ("GET /v1/rfqs", "List RFQs"),
            ("GET /v1/rfqs/{rfq_id}", "Get RFQ"),
            ("POST /v1/rfqs/{rfq_id}/cancel", "Cancel RFQ"),
        ],
    ),
    "Quotes": (
        "A maker's quote on an RFQ, the taker's accept, the maker's confirm, and the acceptance they "
        "create.",
        [
            ("POST /v1/rfqs/{rfq_id}/quotes", "Create quote"),
            ("GET /v1/rfqs/{rfq_id}/quotes", "List quotes"),
            ("DELETE /v1/quotes/{quote_id}", "Cancel quote"),
            ("POST /v1/quotes/{quote_id}/accept", "Accept quote"),
            ("POST /v1/quotes/{quote_id}/confirm", "Confirm quote"),
            ("GET /v1/quotes/{quote_id}/acceptance", "Get acceptance"),
            ("GET /v1/makers/{maker_id}/acceptances", "List acceptances"),
        ],
    ),
    "Positions": (
        "Positions the account holds, or a maker wrote, and the cash-out of one.",
        [
            ("GET /v1/me/positions", "List positions"),
            ("GET /v1/me/positions/{position_id}", "Get position"),
            ("POST /v1/positions/{position_id}/cashout", "Cash out position"),
        ],
    ),
    "Withdrawals": (
        "A withdrawal of Totalis USDC to an external address, in one signed request.",
        [
            ("POST /v1/withdrawals", "Create withdrawal"),
            ("GET /v1/withdrawals/{withdrawal_id}", "Get withdrawal"),
        ],
    ),
    "Account": (
        "The identity, balances, activity and operations of the account a key acts for.",
        [
            ("GET /v1/me", "Get identity"),
            ("GET /v1/me/balances", "Get balances"),
            ("GET /v1/me/activity", "List activity"),
            ("GET /v1/me/operations", "List operations"),
            ("GET /v1/operations/{operation_id}", "Get operation"),
        ],
    ),
    "Makers": (
        "A maker's capital and collateral reductions.",
        [
            ("GET /v1/makers/{maker_id}/capital", "Get maker capital"),
            ("POST /v1/makers/{maker_id}/collateral-reductions", "Create collateral reduction"),
            ("GET /v1/makers/{maker_id}/collateral-reductions/{job_id}", "Get collateral reduction"),
            (
                "POST /v1/makers/{maker_id}/operations/{operation_id}/self-funded-transaction",
                "Submit self-funded transaction",
            ),
        ],
    ),
    "Deployment": (
        "The contract deployment every signature is made against: chain, vault, fees and the USDC domain.",
        [("GET /v1/deployment", "Get deployment")],
    ),
    "Streams": (
        "The authenticated WebSocket for account and maker subscriptions.",
        [("GET /v1/stream", "Open stream")],
    ),
}

# Reads that rebuild state after a reconnect, a truncated snapshot or a lost response.
RECOVERY = {
    "GET /v1/rfqs",
    "GET /v1/rfqs/{rfq_id}",
    "GET /v1/rfqs/{rfq_id}/quotes",
    "GET /v1/quotes/{quote_id}/acceptance",
    "GET /v1/makers/{maker_id}/acceptances",
    "GET /v1/withdrawals/{withdrawal_id}",
    "GET /v1/me/operations",
    "GET /v1/operations/{operation_id}",
}
RECOVERING = (
    "A recovery read. Use it after a reconnect, a snapshot that names it in `truncated`, or a lost "
    "response. The SDK makes it for you. The day-to-day flow never needs it."
)

OPENING = "[Open a position](/hyperliquid/open-a-position)"
CASHING = "[Cash out a position](/hyperliquid/cash-out)"
MAKING = "[Make markets](/hyperliquid/make-markets)"
WITHDRAWING = "[Withdraw](/hyperliquid/withdraw)"

# The SDK equivalent shown on each page of the trading flow.
SDK = {
    "GET /v1/deployment": (
        "`totalis.deployment()` and `maker.deployment()` read it once and cache it. Every flow signs "
        "against it. See [Signing](/hyperliquid/signing)."
    ),
    "GET /v1/stream": (
        "`createTotalis` opens an `account` subscription as `totalis.stream`, and `createMaker` a `maker` "
        "subscription as `maker.stream`. For direct use, `TotalisStream` from "
        "`@totalistrading/hip4-client/realtime`. See [Connect and resume](/hyperliquid/streams)."
    ),
    "POST /v1/rfqs": (
        "`totalis.openPosition({ legs, stake })` creates the RFQ, takes a quote from the stream and "
        f"accepts it. See {OPENING}."
    ),
    "POST /v1/rfqs/{rfq_id}/cancel": (
        "`openPosition` and `cashOut` cancel their RFQ when no acceptable quote arrives within "
        f"`quoteTimeoutMs`, and while recovering a lost accept. See {OPENING}."
    ),
    "POST /v1/positions/{position_id}/cashout": (
        "`totalis.cashOut({ positionId })` creates the cash-out RFQ, takes a quote, has the owner sign "
        f"it and accepts it. See {CASHING}."
    ),
    "POST /v1/quotes/{quote_id}/accept": (
        "`openPosition` and `cashOut` send it once, under an acceptance ID made before the first send, "
        f"and return the result. See {OPENING}."
    ),
    "POST /v1/rfqs/{rfq_id}/quotes": (
        "`maker.quote(rfq, { payout })` creates a quote on an entry RFQ, and `maker.bid(rfq, { price })` "
        f"a quote on a cash-out RFQ. See {MAKING}."
    ),
    "DELETE /v1/quotes/{quote_id}": f"`maker.cancelQuote(quoteId)`. See {MAKING}.",
    "POST /v1/quotes/{quote_id}/confirm": (
        "`maker.onAcceptance(handler)` answers every acceptance with your handler's `\"CONFIRM\"` or "
        f"`\"DECLINE\"`. `maker.confirm(acceptance)` answers one. See {MAKING}."
    ),
    "GET /v1/makers/{maker_id}/capital": (
        "Read it with the typed client: `maker.client.GET(\"/v1/makers/{maker_id}/capital\", ...)`. "
        f"Read it again on `MAKER_CAPITAL_UPDATED`. See {MAKING}."
    ),
    "POST /v1/makers/{maker_id}/collateral-reductions": (
        f"`maker.reduceCollateral({{ signTransaction }})` creates the job and follows it. See {MAKING}."
    ),
    "POST /v1/makers/{maker_id}/operations/{operation_id}/self-funded-transaction": (
        "`maker.reduceCollateral({ signTransaction })` has your gas wallet sign the attestation and "
        f"relays it here. See {MAKING}."
    ),
    "POST /v1/withdrawals": (
        "`totalis.withdraw({ destination, amount })` signs both parts, sends this once and resolves when "
        f"the payout commits. `totalis.waitForWithdrawal(id)` follows one after a restart. See {WITHDRAWING}."
    ),
}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def operations(spec: dict):
    for path, item in spec["paths"].items():
        for method in METHODS:
            if method in item:
                yield f"{method.upper()} {path}", item[method]


def placed() -> dict[str, tuple[str, str]]:
    return {route: (resource, title) for resource, (_, pages) in PAGES.items() for route, title in pages}


def publish(spec: dict) -> dict:
    """File each operation under its resource, title it, and set its URL and SDK or recovery note."""
    pages = placed()
    routes = {key for key, _ in operations(spec)}
    if routes != set(pages):
        raise SystemExit(
            f"PAGES does not match the spec. Unplaced: {sorted(routes - set(pages))}. "
            f"Not in the spec: {sorted(set(pages) - routes)}"
        )
    spec["tags"] = [{"name": resource, "description": description} for resource, (description, _) in PAGES.items()]
    for key, operation in operations(spec):
        resource, title = pages[key]
        operation["tags"] = [resource]
        operation["summary"] = title
        mint = {"href": f"/hyperliquid/api-reference/{slug(resource)}/{slug(title)}"}
        if key in SDK:
            mint["content"] = f"<Tip>\n**SDK:** {SDK[key]}\n</Tip>\n"
        elif key in RECOVERY:
            mint["content"] = f"<Note>\n{RECOVERING}\n</Note>\n"
        operation["x-mint"] = mint
    return spec


def tab() -> dict:
    """The API reference tab: the endpoints overview, then one group per resource."""
    return {
        "tab": TAB,
        "openapi": "/hyperliquid/openapi.json",
        "groups": [{"group": "API reference", "pages": [OVERVIEW]}]
        + [{"group": resource, "pages": [route for route, _ in pages]} for resource, (_, pages) in PAGES.items()],
    }


def with_tab(docs: dict) -> dict:
    product = next(p for p in docs["navigation"]["products"] if p["product"] == PRODUCT)
    index = next(i for i, t in enumerate(product["tabs"]) if t["tab"] == TAB)
    product["tabs"][index] = tab()
    return docs


def dump(value: dict) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--backend", type=Path, help="a hip4-backend checkout: exports its public spec")
    source.add_argument("--spec", type=Path, help="a spec exported by hip4-backend tools/public_openapi.py")
    source.add_argument("--check", action="store_true", help="fail if the committed files are stale")
    args = parser.parse_args()

    if args.backend:
        exported = subprocess.run(
            [sys.executable, "tools/public_openapi.py"], cwd=args.backend, check=True, capture_output=True, text=True
        ).stdout
        spec = json.loads(exported)
    else:
        spec = json.loads((args.spec or SPEC).read_text())

    spec_text = dump(publish(spec))
    docs_text = dump(with_tab(json.loads(DOCS.read_text())))
    if args.check:
        stale = [p.relative_to(ROOT) for p, text in ((SPEC, spec_text), (DOCS, docs_text)) if p.read_text() != text]
        if stale:
            print(f"stale: {', '.join(map(str, stale))}; run scripts/hyperliquid_openapi.py", file=sys.stderr)
            return 1
        return 0
    SPEC.write_text(spec_text)
    DOCS.write_text(docs_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
