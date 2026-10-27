#!/usr/bin/env python3
"""Publish the Hyperliquid API reference: hyperliquid/openapi.json and its tab in docs.json.

The source is hip4-backend's public spec (tools/public_openapi.py), which already leaves out the
app-only routes. This script:

- files every operation under one sidebar group (PAGES), by resource on one axis: Markets,
  RFQs & Quotes, Positions, Account, Makers, Partners & wallet sign-in, API keys, Deployment and WebSocket. The group becomes the
  operation's tag;
- titles every page with one pattern, verb + resource ("Create RFQ", "Accept quote"), replacing
  the spec's summary;
- gives every page a stable URL, /hyperliquid/api-reference/<resource>/<title>, kept by resource so
  regrouping never breaks a link (x-mint);
- drops `additionalProperties: false` from response-only schemas, so a client generated from the spec
  accepts fields added later (requests stay strict);
- writes the API reference tab: an Overview group (OVERVIEW), then one group per PAGES entry, led
  by its hand-written pages (LEADS).

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
METHODS = ("get", "put", "post", "delete", "patch")

# Sidebar groups by resource, one axis, in reading order. Each page is (route, page title, URL
# section); URL sections stay by resource so regrouping never breaks a link.
PAGES: dict[str, tuple[str, list[tuple[str, str, str]]]] = {
    "Markets": (
        "HIP-4 questions and markets, their sides and price history. No API key needed.",
        [
            ("GET /v1/markets", "List markets", "Markets"),
            ("GET /v1/discovery", "List questions", "Markets"),
            ("GET /v1/markets/{outcome_id}", "Get market", "Markets"),
            ("GET /v1/markets/{outcome_id}/history", "Get market history", "Markets"),
        ],
    ),
    "RFQs & Quotes": (
        "RFQs and the quotes that answer them: what a taker calls, then what a maker calls.",
        [
            ("POST /v1/rfqs", "Create RFQ", "RFQs"),
            ("POST /v1/quotes/{quote_id}/accept", "Accept quote", "Quotes"),
            ("POST /v1/rfqs/{rfq_id}/cancel", "Cancel RFQ", "RFQs"),
            ("POST /v1/me/positions/{position_id}/cashout", "Cash out position", "Positions"),
            ("POST /v1/rfqs/{rfq_id}/quotes", "Create quote", "Quotes"),
            ("DELETE /v1/quotes/{quote_id}", "Cancel quote", "Quotes"),
            ("POST /v1/rfqs/{rfq_id}/declines", "Decline RFQ", "RFQs"),
            ("POST /v1/quotes/{quote_id}/confirm", "Confirm quote", "Quotes"),
            ("GET /v1/makers/{maker_id}/acceptances", "List acceptances", "Quotes"),
            ("PUT /v1/makers/{maker_id}/quote-lease", "Keep quote lease", "Quotes"),
            ("DELETE /v1/makers/{maker_id}/quote-lease", "Release quote lease", "Quotes"),
            ("GET /v1/rfqs", "List RFQs", "RFQs"),
            ("GET /v1/rfqs/{rfq_id}", "Get RFQ", "RFQs"),
            ("GET /v1/rfqs/{rfq_id}/quotes", "List quotes", "Quotes"),
            ("GET /v1/quotes/{quote_id}/acceptance", "Get acceptance", "Quotes"),
        ],
    ),
    "Positions": (
        "Positions the account holds, or its maker backs.",
        [
            ("GET /v1/me/positions", "List positions", "Positions"),
            ("GET /v1/me/positions/{position_id}", "Get position", "Positions"),
        ],
    ),
    "Account": (
        "The account a key acts for: identity, balances, activity, operations, withdrawals, deposits and HyperCore exits.",
        [
            ("GET /v1/me", "Get identity", "Account"),
            ("GET /v1/me/balances", "Get balances", "Account"),
            ("GET /v1/me/activity", "List activity", "Account"),
            ("GET /v1/me/pnl", "Get P&L", "Account"),
            ("GET /v1/me/operations", "List operations", "Account"),
            ("GET /v1/me/operations/{operation_id}", "Get operation", "Account"),
            ("POST /v1/me/withdrawals", "Create withdrawal", "Withdrawals"),
            ("POST /v1/me/run-off-claims", "Create run-off claim", "Withdrawals"),
            ("GET /v1/me/withdrawals/{withdrawal_id}", "Get withdrawal", "Withdrawals"),
            ("POST /v1/me/deposits", "Create deposit", "Deposits"),
            ("POST /v1/core-exits", "Create HyperCore exit", "Core exits"),
            ("GET /v1/me/core-exits", "List HyperCore exits", "Core exits"),
            ("GET /v1/core-exits/{exit_id}", "Get HyperCore exit", "Core exits"),
            ("POST /v1/core-exits/{exit_id}/abandon", "Abandon HyperCore exit", "Core exits"),
        ],
    ),
    "Makers": (
        "The rest of a maker's setup after Making: admission, quote history, capital and collateral.",
        [
            ("GET /v1/me/maker", "Get own maker", "Makers"),
            ("POST /v1/me/maker", "Admit own maker", "Makers"),
            ("GET /v1/makers/{maker_id}/quote-history", "List quote history", "Makers"),
            ("GET /v1/makers/{maker_id}/capital", "Get maker capital", "Makers"),
            ("POST /v1/makers/{maker_id}/collateral-reductions", "Create collateral reduction", "Makers"),
            ("GET /v1/makers/{maker_id}/collateral-reductions/{job_id}", "Get collateral reduction", "Makers"),
            ("GET /v1/makers/{maker_id}/withdrawal", "Get maker withdrawal", "Makers"),
            (
                "POST /v1/makers/{maker_id}/operations/{operation_id}/self-funded-transaction",
                "Submit self-funded transaction",
                "Makers",
            ),
        ],
    ),
    "Partners & wallet sign-in": (
        "A partner admits its users' own wallets, which sign in from the partner's pages, and reads its own report.",
        [
            ("POST /v1/partner/wallet-admissions", "Admit wallet", "Partners"),
            ("GET /v1/partner/report", "Get partner report", "Partners"),
            ("POST /v1/auth/wallet-challenges", "Create wallet challenge", "Wallet sessions"),
            ("POST /v1/auth/wallet-sessions", "Create wallet session", "Wallet sessions"),
            ("DELETE /v1/auth/wallet-sessions/current", "End wallet session", "Wallet sessions"),
        ],
    ),
    "API keys": (
        "Issue, rotate and revoke scoped keys from a wallet session. An API key cannot manage keys.",
        [
            ("POST /v1/me/api-key-challenges", "Create API key challenge", "API keys"),
            ("POST /v1/me/api-keys", "Create API key", "API keys"),
            ("POST /v1/me/api-keys/{key_id}/rotations", "Rotate API key", "API keys"),
            ("GET /v1/me/api-keys", "List API keys", "API keys"),
            ("DELETE /v1/me/api-keys/{key_id}", "Revoke API key", "API keys"),
            ("GET /v1/me/api-key-capabilities", "List API key scopes", "API keys"),
            ("POST /v1/makers/{maker_id}/api-key-challenges", "Create maker API key challenge", "API keys"),
            ("POST /v1/makers/{maker_id}/api-keys", "Create maker API key", "API keys"),
            ("POST /v1/makers/{maker_id}/api-keys/{key_id}/rotations", "Rotate maker API key", "API keys"),
            ("GET /v1/makers/{maker_id}/api-keys", "List maker API keys", "API keys"),
            ("DELETE /v1/makers/{maker_id}/api-keys/{key_id}", "Revoke maker API key", "API keys"),
            ("GET /v1/makers/{maker_id}/api-key-capabilities", "List maker API key scopes", "API keys"),
        ],
    ),
    "Deployment": (
        "The contract deployment every signature is made against.",
        [("GET /v1/deployment", "Get deployment", "Deployment")],
    ),
    "WebSocket": (
        "The authenticated WebSocket for account and maker updates.",
        [("GET /v1/stream", "Open stream", "Streams")],
    ),
}

# Hand-written pages that open a reference group, ahead of its generated pages.
OVERVIEW = ["hyperliquid/api-reference/introduction"]

LEADS = {
    "WebSocket": [
        "hyperliquid/api-reference/websocket/connection",
        "hyperliquid/api-reference/websocket/account",
        "hyperliquid/api-reference/websocket/maker",
        "hyperliquid/api-reference/websocket/market-data",
    ],
}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def operations(spec: dict):
    for path, item in spec["paths"].items():
        for method in METHODS:
            if method in item:
                yield f"{method.upper()} {path}", item[method]


# The one group both sides use, split so a taker and a maker each find their calls together.
SUBGROUPS: dict[str, list[tuple[str, int]]] = {
    "RFQs & Quotes": [("Taking", 4), ("Making", 7), ("Reads", 4)],
}


def pages_of(group: str, routes: list[str]) -> list:
    """A group's pages, split into its SUBGROUPS by count, in PAGES order."""
    if group not in SUBGROUPS:
        return routes
    split, start = [], 0
    for name, count in SUBGROUPS[group]:
        split.append({"group": name, "pages": routes[start : start + count]})
        start += count
    if start != len(routes):
        raise SystemExit(f"SUBGROUPS for {group} cover {start} of {len(routes)} pages")
    return split


def placed() -> dict[str, tuple[str, str, str]]:
    return {route: (group, title, section) for group, (_, pages) in PAGES.items() for route, title, section in pages}


# Readable names for the variants of a real union, shown as the option labels on a page.
VARIANT_TITLES = {
    "EntryRfq": "Entry RFQ",
    "CashoutRfq": "Cash-out RFQ",
    "EntryQuote": "Entry quote",
    "SellBackQuote": "Sell-back quote",
    "TransferQuote": "Transfer quote",
    "EntryMakerAcceptance": "Entry acceptance",
    "SellBackMakerAcceptance": "Sell-back acceptance",
    "TransferMakerAcceptance": "Transfer acceptance",
    "ResultUnresolved": "Unresolved",
    "ResultNumeric": "Numeric result",
    "ResultNonnumeric": "Named result",
    "ResultUnavailable": "Result unavailable",
    "ReferenceAvailable": "Available",
    "ReferenceUnavailable": "Reference unavailable",
    "EligibilityEnabled": "Enabled",
    "EligibilityDisabled": "Disabled",
}
UNIONS = ("oneOf", "anyOf")


def is_object(member: dict) -> bool:
    """An object shape, typed or not: it lists its own fields."""
    return member.get("type") in (None, "object") and isinstance(member.get("properties"), dict)


def real_variants(members: list) -> bool:
    """Inline members that are shapes of their own: a scalar or array type, or objects over different fields."""
    if any(member.get("type") not in (None, "object") for member in members):
        return True
    shapes = [frozenset(member["properties"]) for member in members if is_object(member)]
    return len(shapes) > 1 and len(set(shapes)) > 1


def name_variants(members: list) -> None:
    """Title each object variant by its constant (`CONFIRM`) or the field only it has (`entry`)."""
    shapes = [member for member in members if is_object(member)]
    for member in shapes:
        fields = member.get("properties") or {}
        const = next((rule["const"] for rule in fields.values() if isinstance(rule, dict) and isinstance(rule.get("const"), str)), None)
        own = [name for name in fields if not any(name in (other.get("properties") or {}) for other in shapes if other is not member)]
        label = const or (own[0] if own else None)
        if label and "title" not in member:
            member["title"] = label.replace("_", " ").capitalize()


def title_variants(node) -> None:
    """Label the options of every real union; titles are annotations, so every constraint stays."""
    if isinstance(node, list):
        for item in node:
            title_variants(item)
        return
    if not isinstance(node, dict):
        return
    for key in UNIONS:
        members = node.get(key)
        if isinstance(members, list):
            inline = [member for member in members if isinstance(member, dict) and "$ref" not in member]
            if real_variants(inline):
                name_variants(inline)
    for value in node.values():
        title_variants(value)


def readable(spec: dict) -> dict:
    """Title the variants of real unions."""
    title_variants(spec)
    for name, title in VARIANT_TITLES.items():
        if name in spec.get("components", {}).get("schemas", {}):
            spec["components"]["schemas"][name]["title"] = title
    return spec


def schema_refs(spec: dict, node, found: set[str]) -> set[str]:
    """Every component schema node reaches, through $ref, skipping example data."""
    if isinstance(node, list):
        for item in node:
            schema_refs(spec, item, found)
    elif isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            name = ref.rsplit("/", 1)[1]
            if name not in found:
                found.add(name)
                schema_refs(spec, spec["components"]["schemas"][name], found)
        for key, value in node.items():
            if key not in ("example", "examples"):
                schema_refs(spec, value, found)
    return found


def open_object(node) -> None:
    """Drop `additionalProperties: false` from node and every inline schema under it."""
    if isinstance(node, list):
        for item in node:
            open_object(item)
    elif isinstance(node, dict):
        if node.get("additionalProperties") is False:
            del node["additionalProperties"]
        for key, value in node.items():
            if key not in ("example", "examples", "$ref"):
                open_object(value)


def open_responses(spec: dict) -> dict:
    """Responses can gain fields, so their schemas must not promise `additionalProperties: false`.

    Requests stay strict: the API refuses unknown request fields. A schema a request also uses (legs and the
    signed terms) stays strict in both directions, since a new field there would be a new signed type.
    """
    requests: set[str] = set()
    responses: set[str] = set()
    for _, operation in operations(spec):
        schema_refs(spec, [operation.get("requestBody", {}), operation.get("parameters", [])], requests)
        schema_refs(spec, operation.get("responses", {}), responses)
        for response in operation.get("responses", {}).values():
            for media in response.get("content", {}).values():
                if "$ref" not in media.get("schema", {"$ref": ""}):
                    open_object(media["schema"])
    for name in responses - requests:
        open_object(spec["components"]["schemas"][name])
    return spec


def titles(node, path: str = ""):
    """Every schema title under node with where it is, skipping example data."""
    if isinstance(node, list):
        for index, item in enumerate(node):
            yield from titles(item, f"{path}/{index}")
    elif isinstance(node, dict):
        if isinstance(node.get("title"), str):
            yield node["title"], path
        for key, value in node.items():
            if key == "properties" and isinstance(value, dict):
                for name, schema in value.items():
                    yield from titles(schema, f"{path}/properties/{name}")
            elif key not in ("example", "examples", "default", "const", "enum", "x-mint"):
                yield from titles(value, f"{path}/{key}")


def unique_titles(spec: dict) -> None:
    """Stop on a schema title used twice: generated clients name models by title and drop the clash."""
    seen: dict[str, list[str]] = {}
    for title, path in titles({"components": spec.get("components", {}).get("schemas", {}), "paths": spec.get("paths", {})}):
        seen.setdefault(title, []).append(path)
    clashes = {title: paths for title, paths in seen.items() if len(paths) > 1}
    if clashes:
        raise SystemExit(f"Duplicate schema titles: {clashes}. Give each a unique title in VARIANT_TITLES.")


def publish(spec: dict) -> dict:
    """File each operation under its resource, title it, and set its URL."""
    pages = placed()
    routes = {key for key, _ in operations(spec)}
    if routes != set(pages):
        raise SystemExit(
            f"PAGES does not match the spec. Unplaced: {sorted(routes - set(pages))}. "
            f"Not in the spec: {sorted(set(pages) - routes)}"
        )
    spec["tags"] = [{"name": group, "description": description} for group, (description, _) in PAGES.items()]
    for key, operation in operations(spec):
        group, title, section = pages[key]
        operation["tags"] = [group]
        operation["summary"] = title
        # Mintlify titles the sidebar entry from the href slug unless metadata names it: "Get P&L" read "Get p l".
        operation["x-mint"] = {
            "href": f"/hyperliquid/api-reference/{slug(section)}/{slug(title)}",
            "metadata": {"title": title, "sidebarTitle": title},
        }
    return spec


def tab() -> dict:
    """The API reference tab: the overview, then one group per resource, each led by its hand-written pages."""
    return {
        "tab": TAB,
        "openapi": "/hyperliquid/openapi.json",
        "groups": [{"group": "Overview", "pages": OVERVIEW}]
        + [
            {"group": group, "pages": LEADS.get(group, []) + pages_of(group, [route for route, _, _ in pages])}
            for group, (_, pages) in PAGES.items()
        ],
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

    spec = open_responses(readable(publish(spec)))
    unique_titles(spec)
    spec_text = dump(spec)
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
