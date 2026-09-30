#!/usr/bin/env python3
"""Publish the Hyperliquid API reference: hyperliquid/openapi.json and its tab in docs.json.

The source is hip4-backend's public spec (tools/public_openapi.py), which already leaves out the
app-only routes. This script:

- files every operation under one sidebar group (PAGES), by resource on one axis: Markets,
  RFQs & Quotes, Positions, Account, Makers, Deployment and WebSocket. The group becomes the
  operation's tag;
- titles every page with one pattern, verb + resource ("Create RFQ", "Accept quote"), replacing
  the spec's summary;
- gives every page a stable URL, /hyperliquid/api-reference/<resource>/<title>, kept by resource so
  regrouping never breaks a link (x-mint);
- writes the API reference tab: one group per PAGES entry, led by its hand-written pages (LEADS).

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
        "HIP-4 markets, their sides and price history. No API key needed.",
        [
            ("GET /v1/markets", "List markets", "Markets"),
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
            ("POST /v1/quotes/{quote_id}/confirm", "Confirm quote", "Quotes"),
            ("GET /v1/makers/{maker_id}/acceptances", "List acceptances", "Quotes"),
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
        "The account a key acts for: identity, balances, activity, operations and withdrawals.",
        [
            ("GET /v1/me", "Get identity", "Account"),
            ("GET /v1/me/balances", "Get balances", "Account"),
            ("GET /v1/me/activity", "List activity", "Account"),
            ("GET /v1/me/operations", "List operations", "Account"),
            ("GET /v1/me/operations/{operation_id}", "Get operation", "Account"),
            ("POST /v1/me/withdrawals", "Create withdrawal", "Withdrawals"),
            ("GET /v1/me/withdrawals/{withdrawal_id}", "Get withdrawal", "Withdrawals"),
        ],
    ),
    "Makers": (
        "The rest of a maker's setup after Making: capital and collateral.",
        [
            ("GET /v1/makers/{maker_id}/capital", "Get maker capital", "Makers"),
            ("POST /v1/makers/{maker_id}/collateral-reductions", "Create collateral reduction", "Makers"),
            ("GET /v1/makers/{maker_id}/collateral-reductions/{job_id}", "Get collateral reduction", "Makers"),
            (
                "POST /v1/makers/{maker_id}/operations/{operation_id}/self-funded-transaction",
                "Submit self-funded transaction",
                "Makers",
            ),
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
LEADS = {
    "WebSocket": [
        "hyperliquid/websocket/connection",
        "hyperliquid/websocket/account",
        "hyperliquid/websocket/maker",
        "hyperliquid/websocket/market-data",
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
    "RFQs & Quotes": [("Taking", 4), ("Making", 4), ("Reads", 4)],
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
    "ResultUnresolved": "Unresolved",
    "ResultNumeric": "Numeric result",
    "ResultNonnumeric": "Named result",
    "ResultUnavailable": "Unavailable",
    "ReferenceAvailable": "Available",
    "ReferenceUnavailable": "Unavailable",
    "EligibilityEnabled": "Enabled",
    "EligibilityDisabled": "Disabled",
}
COMPOSITIONS = ("oneOf", "anyOf", "allOf")


def condition(branch: dict) -> str:
    """The discriminator a validation branch applies to, as prose, or "" if it has none."""
    for key in ("status", "kind", "series_type", "close_reason"):
        rule = (branch.get("properties") or {}).get(key)
        if isinstance(rule, dict) and "const" in rule:
            return f"`{key}` is `{rule['const']}`"
        if isinstance(rule, dict) and rule.get("enum"):
            return f"`{key}` is " + " or ".join(f"`{value}`" for value in rule["enum"] if value is not None)
    return ""


def plain(text: str) -> str:
    return text.replace("`", "").replace(" only when ", " when ").lower()


def note(prop: dict, text: str) -> None:
    if text and plain(text) not in plain(prop.get("description", "")):
        prop["description"] = (prop.get("description", "").rstrip() + " " + text).strip()


def simplify(node):
    """Docs view of a schema: fold validation-only branches into field descriptions.

    The published contract stays strict for clients that validate (hip4-mm does). Here each
    status- or kind-conditional branch, if/then rule and `false` property becomes a note on the
    field it constrains, so a page shows one object per real variant instead of every rule as an
    option. Unions of named schemas are real variants and stay.
    """
    if isinstance(node, list):
        return [simplify(item) for item in node]
    if not isinstance(node, dict):
        return node
    node = {key: simplify(value) for key, value in node.items()}
    props = node.get("properties") if isinstance(node.get("properties"), dict) else None
    branches = []
    for key in COMPOSITIONS:
        members = node.get(key)
        if not isinstance(members, list):
            continue
        inline = [member for member in members if isinstance(member, dict) and "$ref" not in member]
        branches += inline
        kept = [member for member in members if member not in inline]
        if kept:
            node[key] = kept
        else:
            node.pop(key)
    if isinstance(node.get("then"), dict):
        branches.append({**node["then"], "properties": {**(node.get("if") or {}).get("properties", {}), **node["then"].get("properties", {})}})
    for key in ("if", "then", "else", "not"):
        node.pop(key, None)
    if props is not None:
        for branch in branches:
            when = condition(branch)
            for name in branch.get("required", []):
                if name in props and name not in node.get("required", []) and when:
                    note(props[name], f"Present when {when}.")
            for name, rule in (branch.get("properties") or {}).items():
                if name in props and isinstance(rule, dict) and rule.get("description") and name not in ("status", "kind"):
                    note(props[name], rule["description"])
        node["properties"] = {name: value for name, value in props.items() if value is not False}
        if "required" in node:
            node["required"] = [name for name in node["required"] if name in node["properties"]]
    return node


def readable(spec: dict) -> dict:
    """Simplify every schema for reading and title the variants of real unions."""
    spec = simplify(spec)
    for name, title in VARIANT_TITLES.items():
        if name in spec.get("components", {}).get("schemas", {}):
            spec["components"]["schemas"][name]["title"] = title
    return spec


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
        operation["x-mint"] = {"href": f"/hyperliquid/api-reference/{slug(section)}/{slug(title)}"}
    return spec


def tab() -> dict:
    """The API reference tab: one group per resource, each led by its hand-written pages."""
    return {
        "tab": TAB,
        "openapi": "/hyperliquid/openapi.json",
        "groups": [
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

    spec_text = dump(readable(publish(spec)))
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
