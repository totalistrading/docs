"""Offline checks for signing, price protection and unknown-outcome recovery."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

import python_entry as bot

FIXTURE = json.loads(Path(__file__).with_name("signing-vectors.json").read_text())


class EntryTests(unittest.TestCase):
    def test_contract_known_answer_vectors(self):
        with contextlib.redirect_stdout(io.StringIO()):
            bot.vectors()

    def test_quote_must_match_the_request_price_and_digest(self):
        vector = next(v for v in FIXTURE["vectors"] if v["name"] == "quote_three_legs")
        message = vector["message"]
        entry = {"maker_id": message["makerId"], "stake": message["stake"], "payout": message["payout"],
                 "fee_bps": message["feeBps"], "taker_fee_bps": message["takerFeeBps"], "taker": message["taker"],
                 "expiry": message["expiry"], "salt": message["salt"],
                 "legs": [{"outcome_id": str(leg["outcomeId"]), "side": ["YES", "NO"][leg["side"]]}
                          for leg in message["legs"]]}
        quote = {"kind": "ENTRY", "rfq_id": "request", "quote_id": vector["digest"],
                 "accept_before": "2027-01-15T08:00:00Z", "entry": entry}
        state = {"rfq_id": "request", "wallet": entry["taker"].lower(), "legs": entry["legs"],
                 "stake": entry["stake"], "minimum_payout": "42500000"}
        deployment = {"chain_id": "998", "vault_address": FIXTURE["domain"]["verifyingContract"],
                      "fee_bps": message["feeBps"], "taker_fee_bps": message["takerFeeBps"]}
        self.assertTrue(bot.check_quote(quote, state, deployment, 0))
        self.assertFalse(bot.check_quote(quote, {**state, "minimum_payout": "42500001"}, deployment, 0))
        self.assertFalse(bot.check_quote(quote, {**state, "stake": "6000000"}, deployment, 0))
        tampered = {**quote, "entry": {**entry, "payout": "50000000"}}
        self.assertFalse(bot.check_quote(tampered, state, deployment, 0))
        self.assertFalse(bot.check_quote(quote, state, deployment, bot.timestamp(quote["accept_before"])))

    def test_funding_authorization_is_the_exact_shortfall_and_wallet(self):
        account = bot.Account.create()
        vector = next(v for v in FIXTURE["vectors"] if v["name"] == "quote_three_legs")
        m = vector["message"]
        entry = {"maker_id": m["makerId"], "stake": m["stake"], "payout": m["payout"],
                 "fee_bps": m["feeBps"], "taker_fee_bps": m["takerFeeBps"], "taker": account.address,
                 "expiry": m["expiry"], "salt": m["salt"],
                 "legs": [{"outcome_id": str(leg["outcomeId"]), "side": ["YES", "NO"][leg["side"]]}
                          for leg in m["legs"]]}
        deployment = {"chain_id": "998", "vault_address": FIXTURE["domain"]["verifyingContract"],
                      "usdc": {"eip712_domain": {"name": "USDC", "version": "2", "chain_id": "998",
                                                 "verifying_contract": "0x" + "12" * 20}}}
        quote = {"quote_id": "0x" + "34" * 32, "entry": entry, "_server_time": 1800000000,
                 "_request_started": 0, "accept_before": "2027-01-15T08:00:16Z"}
        with patch.object(bot, "cash", return_value=(2000000, 10000000)), patch.object(bot.time, "monotonic", return_value=0):
            signed = bot.sign_acceptance(None, account, deployment, quote)
        body = json.loads(signed["body_json"])
        funding = body["funding"]
        self.assertEqual(funding["value"], "3000000")
        self.assertEqual(len(funding["authorization_signature"]), 132)
        self.assertIn(funding["authorization_signature"][-2:], ("1b", "1c"))
        recovered = bot.Account.recover_message(
            bot.typed_message(bot.vault_domain(deployment), "TakerAccept", bot.offer_message(entry)),
            signature=body["taker_signature"])
        self.assertEqual(recovered, account.address)
        nonce = bot.keccak(bot.encode(["address", "uint256", "address", "bytes32", "address"],
                          [deployment["vault_address"], 998, account.address,
                           bytes.fromhex(funding["salt"][2:]), account.address]))
        authorization = {"from": account.address, "to": deployment["vault_address"], "value": 3000000,
                         "validAfter": int(funding["valid_after"]), "validBefore": int(funding["valid_before"]),
                         "nonce": nonce}
        domain = {"name": "USDC", "version": "2", "chainId": 998, "verifyingContract": "0x" + "12" * 20}
        recovered = bot.Account.recover_message(bot.typed_message(domain, "ReceiveWithAuthorization", authorization),
                                                signature=funding["authorization_signature"])
        self.assertEqual(recovered, account.address)

    def test_a_quote_that_expires_during_cash_read_is_never_signed(self):
        quote = {"entry": {"stake": "5000000"}, "_server_time": 1800000000,
                 "_request_started": 0, "accept_before": "2027-01-15T08:00:05Z"}
        with patch.object(bot, "cash", return_value=(5000000, 0)), \
             patch.object(bot.time, "monotonic", return_value=10), \
             patch.object(bot, "signature", side_effect=AssertionError("must not sign")):
            with self.assertRaises(bot.QuoteExpired):
                bot.sign_acceptance(None, None, None, quote)

    def test_network_retry_reuses_the_exact_signed_command(self):
        api = bot.Api("staging", "example-key")
        signed = bot.command("/v1/quotes/0x" + "11" * 32 + "/accept", {"taker_signature": "example"})
        seen = []

        def request(method, path, body_json, key):
            seen.append((method, path, body_json, key))
            if len(seen) == 1:
                raise urllib.error.URLError("response lost")
            return {"status": "ACCEPTED"}

        with patch.object(api, "request", side_effect=request), patch.object(bot.time, "sleep"):
            self.assertEqual(api.send(signed)["status"], "ACCEPTED")
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[0], seen[1])

    def test_an_unfenced_404_is_not_a_failed_trade(self):
        class Unfenced:
            def read(self, _):
                raise bot.ApiError(404, {"error": {"code": "NOT_FOUND"}})

            def send(self, _):
                raise bot.ApiError(409, {"error": {"code": "STATE_CONFLICT"}})

        with tempfile.TemporaryDirectory() as directory:
            state = {"quote_id": "quote", "rfq_id": "rfq"}
            with self.assertRaises(bot.ApiError) as caught:
                bot.fenced_acceptance(Unfenced(), state, Path(directory) / "entry.json")
            self.assertEqual(caught.exception.code, "STATE_CONFLICT")

    def test_resume_recovers_and_reconciles_without_signing(self):
        acceptance = {"status": "ACCEPTED", "acceptance_id": "same-key", "quote_id": "quote",
                      "rfq_id": "rfq", "operation_id": "operation"}

        class LostResponse:
            def send(self, command):
                self.command = command
                raise urllib.error.URLError("response lost")

            def read(self, path):
                if path.endswith("/acceptance"):
                    return acceptance
                if path.endswith("/operations/operation"):
                    return {"operation": {"status": "COMMITTED", "operation_id": "operation"}}
                if path.endswith("/positions/quote"):
                    return {"context": {"status": "CURRENT"}, "position": {"position_id": "quote"}}
                raise AssertionError(path)

        api = LostResponse()
        state = {"phase": "ACCEPT", "quote_id": "quote", "rfq_id": "rfq",
                 "accept": {"key": "same-key", "path": "/v1/quotes/quote/accept", "body_json": "saved bytes"}}
        with tempfile.TemporaryDirectory() as directory, patch.object(bot, "signature", side_effect=AssertionError("must not sign")):
            path = Path(directory) / "entry.json"
            with contextlib.redirect_stdout(io.StringIO()):
                bot.finish(api, state, path)
            saved = json.loads(path.read_text())
            self.assertEqual(saved["result"]["status"], "COMMITTED")
            self.assertEqual(saved["accept"], api.command)
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_market_detail_envelope_and_numeric_order(self):
        class Markets:
            def read(self, path, public=False):
                return {"market": {"state": "ACTIVE", "eligibility": {"state": "ENABLED"},
                                   "combo": {"state": "OPEN"}, "native_question_id": None}}
        bot.validate_legs(Markets(), [{"outcome_id": "9", "side": "YES"}, {"outcome_id": "10", "side": "NO"}])
        with self.assertRaises(ValueError):
            bot.validate_legs(Markets(), [{"outcome_id": "10", "side": "YES"}, {"outcome_id": "9", "side": "NO"}])


if __name__ == "__main__":
    unittest.main()
