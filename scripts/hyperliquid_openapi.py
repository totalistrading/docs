#!/usr/bin/env python3
"""Publish the Hyperliquid API reference: hyperliquid/openapi.json and its tab in docs.json.

The source is hip4-backend's public spec (tools/public_openapi.py). This script:

- drops the routes the public docs do not show (HIDDEN): app-only maker access and onboarding
  reads, and the taker self-funded transaction route, since Totalis sponsors taker gas. The API
  keeps them. The maker self-funded route stays: makers pay their own gas and relay through it;
- gives every operation a stable URL, /hyperliquid/api-reference/<tag>/<summary>, and puts the
  SDK equivalent on the pages of the trading flow (x-mint);
- writes the API reference tab: the taker and maker trading flow first, everything else in
  collapsed reference groups. A route no rule places lands in a group named after its tag.

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
OVERVIEW = "hyperliquid/trading-api"
METHODS = ("get", "put", "post", "delete", "patch")

# Routes the API serves but the public docs do not show.
HIDDEN = {
    # Maker access and onboarding: the Totalis app reads these, an API key cannot use them.
    "GET /v1/me/maker",
    "GET /v1/me/controlled-makers",
    "GET /v1/me/makers",
    "GET /v1/maker-onboarding/registrations/{maker_id}",
    # Takers do not pay their own gas: Totalis sponsors it.
    "POST /v1/operations/{operation_id}/self-funded-transaction",
}

# The Totalis withdrawal, kept as one group so it can shrink to one call without touching the rest.
WITHDRAW = [
    "POST /v1/totalis-withdrawals",
    "GET /v1/totalis-withdrawals/{continuation_id}",
    "POST /v1/totalis-withdrawals/{continuation_id}/payout-claim",
    "POST /v1/totalis-withdrawals/{continuation_id}/payout-submission",
]

TAKER = [
    "GET /v1/vault",
    "POST /v1/deposits",
    "GET /v1/stream",
    "POST /v1/rfqs",
    "POST /v1/rfqs/{rfq_id}/attempts/{attempt_id}",
    "POST /v1/rfqs/{rfq_id}/cancel",
    "POST /v1/tickets/{ticket_id}/claims",
    {"group": "Withdraw", "pages": WITHDRAW},
]

MAKER = [
    "GET /v1/makers/{maker_id}/capital",
    "GET /v1/stream",
    "POST /v1/rfqs/{rfq_id}/book-quotes",
    "DELETE /v1/rfqs/{rfq_id}/book-quotes/{quote_digest}",
    "POST /v1/rfqs/{rfq_id}/attempts/{attempt_id}/confirmation",
]

RECOVERY = "Recovery (the SDK does this for you)"

# Reference groups, in nav order. A route goes to the group its path names in PLACED, else to the
# group its tag names in BY_TAG, else to a group named after its tag.
REFERENCE = ["Market data", "Account", "Operations", "Funds and tickets", "Maker", "HyperCore", RECOVERY]
BY_TAG = {
    "Market data": "Market data",
    "Identity": "Account",
    "Account": "Account",
    "Funds and tickets": "Funds and tickets",
    "Maker reads": "Maker",
    "HyperCore": "HyperCore",
    "Recovery": RECOVERY,
}
PLACED = {
    "GET /v1/me/operations": "Operations",
    "GET /v1/operations/{operation_id}": "Operations",
    "GET /v1/makers/{maker_id}/operations": "Operations",
    "GET /v1/makers/{maker_id}/operations/{operation_id}": "Operations",
    "GET /v1/makers/{maker_id}/funding-transaction": "Maker",
    "GET /v1/makers/{maker_id}/collateral-reductions/{job_id}": "Maker",
    "POST /v1/makers/{maker_id}/collateral-reductions": "Maker",
    "POST /v1/makers/{maker_id}/operations/{operation_id}/self-funded-transaction": "Maker",
    "GET /v1/makers/{maker_id}/offers": "Maker",
    "GET /v1/makers/{maker_id}/snapshot": RECOVERY,
    "GET /v1/makers/{maker_id}/events": RECOVERY,
}

TRADING = "[Trading](/hyperliquid/trading)"
MAKING = "[Market makers](/hyperliquid/market-makers)"
FUNDING = "[Funding](/hyperliquid/funding)"
WITHDRAWING = "[Funding](/hyperliquid/funding#withdraw-to-any-address)"
RECOVERING = (
    "A recovery read. The SDK makes it for you after a reconnect, a truncated snapshot, or a lost "
    "response. The day-to-day flow never needs it."
)

# The SDK equivalent shown on each page of the trading flow.
SDK = {
    "GET /v1/vault": f"Every SDK flow reads this for you and caches it as `totalis.release()`. See {TRADING}.",
    "POST /v1/deposits": (
        f"`totalis.deposit({{ amount }})`. `placeBet` can also fund a vault shortfall in its accept, "
        f"so a separate deposit is optional. See {FUNDING}."
    ),
    "GET /v1/stream": (
        "`createTotalis` and `createMaker` open it for you as `totalis.stream` and `maker.stream`. "
        "For direct use, `TotalisStream` from `@totalistrading/hip4-client/realtime`. "
        "See [Realtime](/hyperliquid/realtime)."
    ),
    "POST /v1/rfqs": (
        "`totalis.placeBet({ legs, stake })` creates an entry RFQ and `totalis.cashOut({ ticketId })` "
        f"a cash-out RFQ. Each then takes an offer from the book and accepts it. See {TRADING}."
    ),
    "POST /v1/rfqs/{rfq_id}/attempts/{attempt_id}": (
        "`totalis.placeBet` sends this with a quote and `totalis.cashOut` with a bid, and each returns "
        f"its final result. See {TRADING}."
    ),
    "POST /v1/rfqs/{rfq_id}/cancel": (
        "`placeBet` and `cashOut` cancel their RFQ when no acceptable offer arrives within "
        f"`quoteTimeoutMs`, and while recovering a lost accept. See {TRADING}."
    ),
    "POST /v1/tickets/{ticket_id}/claims": (
        f"`totalis.claimTicket(ticketId)`. Totalis also claims settled tickets on its own. See {TRADING}."
    ),
    "GET /v1/makers/{maker_id}/capital": (
        "Read it with the typed client: `maker.client.GET(\"/v1/makers/{maker_id}/capital\", ...)`. "
        f"Re-read it on `MAKER_VAULT_UPDATED`. See {MAKING}."
    ),
    "POST /v1/rfqs/{rfq_id}/book-quotes": (
        "`maker.quote(rfq, { payout })` publishes a quote on an entry RFQ, and "
        f"`maker.bid(rfq, {{ price }})` a bid on a cash-out RFQ. See {MAKING}."
    ),
    "DELETE /v1/rfqs/{rfq_id}/book-quotes/{quote_digest}": f"`maker.withdraw(rfqId, quoteDigest)`. See {MAKING}.",
    "POST /v1/makers/{maker_id}/operations/{operation_id}/self-funded-transaction": (
        "`maker.reduceCollateral({ signTransaction })` signs the collateral reduction's attestation with "
        f"your gas wallet and relays it here. See {MAKING}."
    ),
    "POST /v1/rfqs/{rfq_id}/attempts/{attempt_id}/confirmation": (
        "`maker.onConfirmation(handler)` answers every confirmation request with your handler's "
        f"`\"CONFIRM\"` or `\"DECLINE\"`. `maker.confirm(request)` answers one. See {MAKING}."
    ),
    **{key: f"`totalis.withdraw({{ destination, amount }})` runs all four withdrawal calls, and "
       f"`totalis.resumeWithdrawal` continues one after a restart. See {WITHDRAWING}." for key in WITHDRAW},
}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def operations(spec: dict):
    for path, item in spec["paths"].items():
        for method in METHODS:
            if method in item:
                yield f"{method.upper()} {path}", item[method]


def refs(node) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        if isinstance(node.get("$ref"), str):
            found.add(node["$ref"])
        for value in node.values():
            found |= refs(value)
    elif isinstance(node, list):
        for value in node:
            found |= refs(value)
    return found


def reachable(spec: dict) -> set[str]:
    """Every component pointer reachable from outside components."""
    seen: set[str] = set()
    todo = refs({key: value for key, value in spec.items() if key != "components"})
    while todo:
        ref = todo.pop()
        if ref in seen or not ref.startswith("#/components/"):
            continue
        seen.add(ref)
        _, _, kind, name = ref.split("/", 3)
        todo |= refs(spec["components"].get(kind, {}).get(name))
    return seen


def publish(spec: dict) -> dict:
    """Drop the hidden routes and what only they used, then set each page's URL and SDK note."""
    before = reachable(spec)
    for key in HIDDEN:
        method, path = key.split(" ", 1)
        item = spec["paths"].get(path, {})
        item.pop(method.lower(), None)
        if not any(method in item for method in METHODS):
            spec["paths"].pop(path, None)
    orphaned = before - reachable(spec)
    for ref in orphaned:
        _, _, kind, name = ref.split("/", 3)
        del spec["components"][kind][name]
    used = {tag for _, operation in operations(spec) for tag in operation.get("tags", [])}
    spec["tags"] = [tag for tag in spec.get("tags", []) if tag["name"] in used]

    for key, operation in operations(spec):
        mint = {"href": f"/hyperliquid/api-reference/{slug(operation['tags'][0])}/{slug(operation['summary'])}"}
        if key in SDK:
            mint["content"] = f"<Tip>\n**SDK:** {SDK[key]}\n</Tip>\n"
        elif RECOVERY in (PLACED.get(key), BY_TAG.get(operation["tags"][0])):
            mint["content"] = f"<Note>\n{RECOVERING}\n</Note>\n"
        operation["x-mint"] = mint
    return spec


def flow_keys(pages: list) -> set[str]:
    keys: set[str] = set()
    for page in pages:
        keys |= flow_keys(page["pages"]) if isinstance(page, dict) else {page}
    return keys


def tab(spec: dict) -> dict:
    """The API reference tab: the trading flow, then every other route in a collapsed group."""
    keys = [key for key, _ in operations(spec)]
    flow = flow_keys(TAKER) | flow_keys(MAKER)
    missing = flow - set(keys)
    if missing:
        raise SystemExit(f"the trading flow names routes the spec does not have: {sorted(missing)}")
    groups: dict[str, list[str]] = {name: [] for name in REFERENCE}
    for key, operation in operations(spec):
        if key in flow:
            continue
        tag = operation["tags"][0]
        groups.setdefault(PLACED.get(key) or BY_TAG.get(tag, tag), []).append(key)
    return {
        "tab": TAB,
        "openapi": "/hyperliquid/openapi.json",
        "groups": [
            {
                "group": "Trading API",
                "pages": [
                    OVERVIEW,
                    {"group": "Taker", "expanded": True, "pages": TAKER},
                    {"group": "Maker", "expanded": True, "pages": MAKER},
                ],
            },
            {
                "group": "Reference",
                "pages": [{"group": name, "pages": pages} for name, pages in groups.items() if pages],
            },
        ],
    }


def with_tab(docs: dict, spec: dict) -> dict:
    product = next(p for p in docs["navigation"]["products"] if p["product"] == PRODUCT)
    index = next(i for i, t in enumerate(product["tabs"]) if t["tab"] == TAB)
    product["tabs"][index] = tab(spec)
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
    docs_text = dump(with_tab(json.loads(DOCS.read_text()), spec))
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
