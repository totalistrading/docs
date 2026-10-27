#!/usr/bin/env python3
"""One RFQ entry over HTTP, with EIP-712 signing and a durable retry journal.

`markets` is public and read-only. `entry` previews unless --execute is supplied.
`resume` retries only the saved command; it never requests another signature.
This example funds from HyperEVM wallet/vault USDC. It does not bridge HyperCore.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from eth_abi import encode
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak

HOSTS = {
    "production": "https://hip4-api.totalis.trade",
    "staging": "https://hip4-api-staging.totalis.trade",
}
OFFER = [
    ("makerId", "uint64"), ("legs", "Leg[]"), ("stake", "uint128"),
    ("payout", "uint128"), ("feeBps", "uint16"), ("takerFeeBps", "uint16"),
    ("taker", "address"), ("expiry", "uint64"), ("salt", "uint256"),
]
TYPES = {
    "Leg": [("outcomeId", "uint32"), ("side", "uint8")],
    "Quote": OFFER,
    "TakerAccept": OFFER,
    "SellBack": [("ticketId", "bytes32"), ("price", "uint128"), ("owner", "address"),
                 ("expiry", "uint64"), ("salt", "uint256"), ("legState", "bytes32")],
    "CashoutTransfer": [("ticketId", "bytes32"), ("price", "uint128"),
                        ("seller", "address"), ("buyer", "address"),
                        ("expiry", "uint64"), ("salt", "uint256"), ("legState", "bytes32")],
    "Exit": [("account", "address"), ("to", "address"), ("amount", "uint128"),
             ("expiry", "uint64"), ("salt", "uint256")],
    "ReceiveWithAuthorization": [("from", "address"), ("to", "address"), ("value", "uint256"),
                                 ("validAfter", "uint256"), ("validBefore", "uint256"), ("nonce", "bytes32")],
}


def typed_message(domain, primary, message):
    names = [primary, "Leg"] if primary in ("Quote", "TakerAccept") else [primary]
    return encode_typed_data(full_message={
        "domain": domain, "primaryType": primary, "message": message,
        "types": {name: [{"name": n, "type": t} for n, t in TYPES[name]] for name in names},
    })


def vault_domain(deployment):
    return {"name": "TotalisParlay", "version": "1", "chainId": int(deployment["chain_id"]),
            "verifyingContract": deployment["vault_address"]}


def offer_message(entry):
    return {
        "makerId": int(entry["maker_id"]),
        "legs": [{"outcomeId": int(leg["outcome_id"]), "side": {"YES": 0, "NO": 1}[leg["side"]]}
                 for leg in entry["legs"]],
        "stake": int(entry["stake"]), "payout": int(entry["payout"]),
        "feeBps": entry["fee_bps"], "takerFeeBps": entry["taker_fee_bps"],
        "taker": entry["taker"], "expiry": int(entry["expiry"]), "salt": int(entry["salt"]),
    }


def digest(message):
    return "0x" + keccak(b"\x19" + message.version + message.header + message.body).hex()


def signature(account, message):
    return "0x" + account.sign_message(message).signature.hex()


def uuid7():
    # RFC 9562: Unix milliseconds, version 7, random bits, RFC variant.
    value = ((time.time_ns() // 1_000_000) << 80) | (7 << 76)
    value |= secrets.randbits(12) << 64
    value |= 2 << 62 | secrets.randbits(62)
    return str(uuid.UUID(int=value))


def timestamp(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


class ApiError(Exception):
    def __init__(self, status, body, retry_after=None):
        error = body.get("error", {}) if isinstance(body, dict) else {}
        self.status, self.code = status, error.get("code", "HTTP_ERROR")
        self.retry = error.get("retry", "BACKOFF" if status in (429, 503) else "NEVER")
        self.retry_after = retry_after
        super().__init__(f"HTTP {status} {self.code}")


class Api:
    def __init__(self, environment, key=None):
        self.environment, self.base, self.key = environment, HOSTS[environment], key

    def request(self, method, path, body_json=None, key=None, public=False):
        headers = {"Accept": "application/json"}
        if not public:
            if not self.key:
                raise ValueError("Set TOTALIS_API_KEY for account calls")
            headers["Authorization"] = "Bearer " + self.key
        if key:
            headers["Idempotency-Key"] = key
        data = body_json.encode() if body_json is not None else None
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            try:
                body = json.loads(error.read())
            except (ValueError, UnicodeDecodeError):
                body = {}
            raise ApiError(error.code, body, error.headers.get("Retry-After")) from None

    def read(self, path, public=False):
        return self.request("GET", path, public=public)

    def send(self, command):
        # Every attempt uses the exact same serialized body and command key.
        for attempt in range(5):
            try:
                return self.request("POST", command["path"], command["body_json"], command["key"])
            except ApiError as error:
                if error.retry != "BACKOFF" or attempt == 4:
                    raise
                delay = float(error.retry_after) if error.retry_after else 2 ** attempt
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt == 4:
                    raise
                delay = 2 ** attempt
            time.sleep(delay)
        raise RuntimeError("unreachable")


def command(path, body=None):
    return {"path": path, "key": uuid7(), "body_json": None if body is None else json.dumps(body, separators=(",", ":"))}


def save(path, state):
    # Atomic replace and fsync ensure the signed command is durable before POST.
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as file:
        json.dump(state, file, separators=(",", ":"))
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, target)
    directory = os.open(target.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


@contextlib.contextmanager
def locked(path):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(str(target) + ".lock", "a") as file:
        fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def eligible(market):
    return (market.get("state") == "ACTIVE" and market.get("eligibility", {}).get("state") == "ENABLED"
            and market.get("combo", {}).get("state") == "OPEN")


def markets(api):
    cursor = None
    while True:
        query = {"limit": 200}
        if cursor:
            query["cursor"] = cursor
        page = api.read("/v1/markets?" + urllib.parse.urlencode(query), public=True)
        for market in page["items"]:
            if eligible(market):
                print(json.dumps({name: market[name] for name in ("outcome_id", "native_question_id", "title")}))
        if not page["has_more"]:
            break
        cursor = page["next_cursor"]


def validate_legs(api, legs):
    if not isinstance(legs, list) or not legs:
        raise ValueError("legs must be a nonempty JSON array")
    ids = []
    yes_questions = set()
    for leg in legs:
        if set(leg) != {"outcome_id", "side"} or leg["side"] not in ("YES", "NO"):
            raise ValueError("each leg needs outcome_id and YES or NO side")
        outcome = leg["outcome_id"]
        if not isinstance(outcome, str) or str(int(outcome)) != outcome or not 0 <= int(outcome) <= 0xffffffff:
            raise ValueError("outcome_id must be a canonical uint32 decimal string")
        ids.append(int(outcome))
        market = api.read("/v1/markets/" + outcome, public=True)["market"]
        if not eligible(market):
            raise ValueError(f"outcome {outcome} does not currently admit RFQ entries")
        question = market.get("native_question_id")
        if question is not None and leg["side"] == "YES":
            if question in yes_questions:
                raise ValueError("two YES outcomes of the same question cannot both win")
            yes_questions.add(question)
    if ids != sorted(set(ids)):
        raise ValueError("legs must have unique outcome_ids in numeric ascending order")


def cash(api):
    balance = api.read("/v1/me/balances")
    if balance["state"] != "CURRENT" or balance["pending"]["has_unknown_operations"]:
        raise ValueError("wait for a current balance with no unknown operations")
    components = {row["kind"]: int(row["amount"]) for row in balance["components"]
                  if row["state"] == "CURRENT" and row["amount"] is not None}
    if set(components) != {"WALLET_USDC", "VAULT_FREE"}:
        raise ValueError("a balance component is unreadable")
    return components["VAULT_FREE"], max(0, components["WALLET_USDC"] - int(balance["pending"]["wallet_reserved"]))


def check_quote(quote, state, deployment, now):
    entry = quote.get("entry", {})
    if quote.get("kind") != "ENTRY" or quote.get("rfq_id") != state["rfq_id"]:
        return False
    if entry.get("legs") != state["legs"] or entry.get("stake") != state["stake"]:
        return False
    if entry.get("taker", "").lower() != state["wallet"]:
        return False
    if (entry.get("fee_bps"), entry.get("taker_fee_bps")) != (deployment["fee_bps"], deployment["taker_fee_bps"]):
        return False
    if int(entry["payout"]) < int(state["minimum_payout"]) or timestamp(quote["accept_before"]) <= now:
        return False
    return digest(typed_message(vault_domain(deployment), "Quote", offer_message(entry))) == quote["quote_id"]


class QuoteExpired(ValueError):
    pass


def quote_now(quote):
    # Conservatively include the whole HTTP round trip, plus later local work.
    return quote["_server_time"] + time.monotonic() - quote["_request_started"]


def sign_acceptance(api, account, deployment, quote):
    entry = quote["entry"]
    vault, wallet = cash(api)
    shortfall = max(0, int(entry["stake"]) - vault)
    if shortfall > wallet:
        raise ValueError("not enough HyperEVM USDC; this example does not bridge HyperCore")
    if quote_now(quote) >= timestamp(quote["accept_before"]):
        raise QuoteExpired("quote expired while checking cash")
    body = {"taker_signature": signature(account, typed_message(vault_domain(deployment), "TakerAccept", offer_message(entry)))}
    if shortfall:
        # Use the server's observed time for validAfter, not an upper-bound clock
        # estimate that could be ahead of the venue. expiry bounds validBefore.
        now = int(quote["_server_time"])
        salt = secrets.token_bytes(32)
        nonce = keccak(encode(["address", "uint256", "address", "bytes32", "address"],
                              [deployment["vault_address"], int(deployment["chain_id"]), account.address, salt, account.address]))
        authorization = {"from": account.address, "to": deployment["vault_address"], "value": shortfall,
                         "validAfter": now - 1, "validBefore": int(entry["expiry"]), "nonce": nonce}
        usdc = deployment["usdc"]["eip712_domain"]
        domain = {"name": usdc["name"], "version": usdc["version"], "chainId": int(usdc["chain_id"]),
                  "verifyingContract": usdc["verifying_contract"]}
        body["funding"] = {"kind": "WALLET", "value": str(shortfall), "valid_after": str(authorization["validAfter"]),
                           "valid_before": str(authorization["validBefore"]), "salt": "0x" + salt.hex(),
                           "authorization_signature": signature(account, typed_message(domain, "ReceiveWithAuthorization", authorization))}
    if quote_now(quote) >= timestamp(quote["accept_before"]):
        raise QuoteExpired("quote expired while signing")
    return command("/v1/quotes/" + quote["quote_id"] + "/accept", body)


def fenced_acceptance(api, state, path):
    read_path = "/v1/quotes/" + state["quote_id"] + "/acceptance"
    try:
        return api.read(read_path)
    except ApiError as error:
        if error.status != 404:
            raise
    state.setdefault("cancel", command("/v1/rfqs/" + state["rfq_id"] + "/cancel"))
    save(path, state)
    # A cancel fences a delayed accept. STATE_CONFLICT does not fence it.
    unfenced = None
    try:
        api.send(state["cancel"])
    except ApiError as error:
        if error.code not in ("RFQ_NOT_CANCELLABLE", "NOT_FOUND"):
            if error.code != "STATE_CONFLICT":
                raise
            unfenced = error
    try:
        return api.read(read_path)
    except ApiError as error:
        if error.status == 404:
            if unfenced:
                raise unfenced
            return {"status": "NOT_ADMITTED"}
        raise


def finish(api, state, path):
    if state["phase"] == "DONE":
        print(json.dumps(state["result"]))
        return
    if "accept" not in state:
        # A restart before signing stops the RFQ. It never signs an old quote.
        if "rfq_id" not in state:
            state["rfq_id"] = api.send(state["create"])["rfq_id"]
            save(path, state)
        state.setdefault("cancel", command("/v1/rfqs/" + state["rfq_id"] + "/cancel"))
        save(path, state)
        try:
            api.send(state["cancel"])
        except ApiError as error:
            if error.code not in ("RFQ_NOT_CANCELLABLE", "NOT_FOUND"):
                raise
        state.update(phase="DONE", result={"status": "CANCELLED_BEFORE_SIGNING"})
        save(path, state)
        print(json.dumps(state["result"]))
        return
    try:
        acceptance = api.send(state["accept"])
    except (ApiError, urllib.error.URLError, TimeoutError, OSError):
        # A lost or refused replay is never grounds to issue a second accept.
        acceptance = fenced_acceptance(api, state, path)
    while acceptance["status"] == "PENDING_CONFIRM":
        time.sleep(0.5)
        acceptance = api.read("/v1/quotes/" + state["quote_id"] + "/acceptance")
    if acceptance["status"] != "NOT_ADMITTED":
        if (acceptance["acceptance_id"] != state["accept"]["key"]
                or acceptance["quote_id"] != state["quote_id"] or acceptance["rfq_id"] != state["rfq_id"]):
            raise ValueError("acceptance identity does not match the saved command")
    state["acceptance"] = acceptance
    save(path, state)
    operation_id = acceptance.get("operation_id")
    if operation_id:
        while True:
            operation = api.read("/v1/me/operations/" + operation_id)["operation"]
            state["operation"] = operation
            save(path, state)
            if operation["status"] in ("COMMITTED", "REVERTED", "EXPIRED_UNEXECUTED"):
                break
            time.sleep(1)
        if operation["status"] == "COMMITTED":
            # Current positions use an evidence freshness envelope.
            state["position"] = api.read("/v1/me/positions/" + state["quote_id"])
        else:
            state["rfq"] = api.read("/v1/rfqs/" + state["rfq_id"])
    state.update(phase="DONE", result={"status": state.get("operation", acceptance)["status"],
                                      "rfq_id": state["rfq_id"], "quote_id": state["quote_id"],
                                      "operation_id": operation_id})
    save(path, state)
    print(json.dumps(state["result"]))


def entry(api, args):
    if Path(args.state).exists():
        raise ValueError("state already exists; use resume instead of creating another trade")
    legs = json.loads(Path(args.legs).read_text())
    validate_legs(api, legs)
    me = api.read("/v1/me")
    deployment = api.read("/v1/deployment", public=True)
    if any(deployment[name] is None for name in ("fee_bps", "taker_fee_bps")):
        raise ValueError("deployment fees are not available")
    vault, wallet = cash(api)
    if int(args.stake) <= 0 or int(args.minimum_payout) <= 0:
        raise ValueError("stake and minimum-payout must be positive atomic USDC")
    if vault + wallet < int(args.stake):
        raise ValueError("not enough HyperEVM USDC; read the funding guide before trading")
    if not args.execute:
        print(json.dumps({"preview": True, "wallet": me["wallet"], "legs": legs, "stake": args.stake,
                          "minimum_payout": args.minimum_payout, "vault": str(vault), "wallet_usdc": str(wallet)}))
        return
    account = Account.from_key(os.environ["TOTALIS_WALLET_KEY"])
    if account.address.lower() != me["wallet"].lower():
        raise ValueError("TOTALIS_WALLET_KEY does not match GET /v1/me wallet")
    state = {"version": 1, "environment": args.environment, "wallet": me["wallet"].lower(), "phase": "RFQ",
             "legs": legs, "stake": args.stake, "minimum_payout": args.minimum_payout,
             "create": command("/v1/rfqs", {"stake": args.stake, "legs": legs})}
    save(args.state, state)
    state["rfq_id"] = api.send(state["create"])["rfq_id"]
    state["phase"] = "QUOTING"
    save(args.state, state)
    deadline = time.monotonic() + args.quote_wait
    while time.monotonic() < deadline:
        request_started = time.monotonic()
        page = api.read("/v1/rfqs/" + state["rfq_id"] + "/quotes")
        now = timestamp(page["server_time"])
        deployment = api.read("/v1/deployment", public=True)
        candidates = [quote for quote in page["quotes"] if check_quote(quote, state, deployment, now + time.monotonic() - request_started)]
        if candidates:
            quote = max(candidates, key=lambda value: int(value["entry"]["payout"]))
            quote["_server_time"] = now
            quote["_request_started"] = request_started
            state["quote_id"] = quote["quote_id"]
            try:
                signed = sign_acceptance(api, account, deployment, quote)
            except QuoteExpired:
                finish(api, state, args.state)
                return
            state["accept"] = signed
            state["phase"] = "ACCEPT"
            save(args.state, state)
            finish(api, state, args.state)
            return
        time.sleep(0.5)
    # No qualifying price. Finish cancels the RFQ without signing.
    finish(api, state, args.state)


def vectors():
    fixtures = json.loads(Path(__file__).with_name("signing-vectors.json").read_text())
    for vector in fixtures["vectors"]:
        message = typed_message(fixtures["domain"], vector["primaryType"], vector["message"])
        assert "0x" + message.header.hex() == fixtures["domainSeparator"]
        assert "0x" + message.body.hex() == vector["structHash"], vector["name"]
        assert digest(message) == vector["digest"], vector["name"]
        assert Account.recover_message(message, signature=vector["signature"]).lower() == fixtures["signer"].lower()
    print(f"Verified {len(fixtures['vectors'])} signing vectors offline")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", choices=HOSTS, default="staging")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("markets")
    sub.add_parser("vectors")
    create = sub.add_parser("entry")
    create.add_argument("--legs", required=True, help="path to an array of outcome_id/side pairs")
    create.add_argument("--stake", required=True, help="atomic USDC string")
    create.add_argument("--minimum-payout", required=True, help="minimum gross payout in atomic USDC")
    create.add_argument("--state", required=True)
    create.add_argument("--quote-wait", type=float, default=10, help="local polling budget in seconds")
    create.add_argument("--execute", action="store_true", help="sign and send the entry")
    resume = sub.add_parser("resume")
    resume.add_argument("--state", required=True)
    args = parser.parse_args()
    if args.action == "vectors":
        vectors()
        return
    api = Api(args.environment, os.environ.get("TOTALIS_API_KEY"))
    if args.action == "markets":
        markets(api)
        return
    with locked(args.state):
        if args.action == "entry":
            entry(api, args)
        else:
            state = json.loads(Path(args.state).read_text())
            me = api.read("/v1/me")
            if state.get("version") != 1 or state["environment"] != args.environment or state["wallet"] != me["wallet"].lower():
                raise ValueError("journal version, environment or account does not match")
            finish(api, state, args.state)


if __name__ == "__main__":
    try:
        main()
    except (ApiError, ValueError, KeyError, OSError, urllib.error.URLError) as error:
        print(f"Stopped: {error}. Keep the journal and use resume for any unresolved command.", file=sys.stderr)
        sys.exit(1)
