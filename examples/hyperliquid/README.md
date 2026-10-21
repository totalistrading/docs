# Python RFQ entry

Run one entry with HTTP and EIP-712 signing, then resume the same saved commands after a restart.
See [API trading](https://docs.totalis.trade/hyperliquid/guides/api-trading) for the account, funding,
permission and lifecycle contracts. Python 3.10 or later on macOS/Linux is required.

```bash
python3 -m venv .venv
.venv/bin/pip install -r examples/hyperliquid/requirements.txt
.venv/bin/python examples/hyperliquid/python_entry.py vectors
.venv/bin/python -m unittest discover -s examples/hyperliquid -p 'test_*.py'
.venv/bin/python examples/hyperliquid/python_entry.py --environment staging markets
```

The vectors run offline. `markets` only reads public market data. It pages the catalog and prints eligible
markets; choose the legs and sides yourself, read their rules, and write an array in `legs.json`:

```json
[{"outcome_id":"<current eligible outcome ID>","side":"YES"}]
```

Replace the placeholder with a live outcome ID. For a combo, add legs in numeric outcome order. The example
rejects duplicate outcomes and two YES outcomes from one question. An RFQ may still receive no quote.

Load `TOTALIS_API_KEY` from your secret store. The key needs the recommended
[taker scopes](https://docs.totalis.trade/hyperliquid/authentication#scopes), including `rfq:read`.
The default environment is staging. Staging credentials and test money are separate from production.

```bash
.venv/bin/python examples/hyperliquid/python_entry.py --environment staging entry \
  --legs legs.json --stake 5000000 --minimum-payout 10000000 --state entry.json
```

Without `--execute`, this only validates markets, identity and current HyperEVM cash. To submit this entry,
load `TOTALIS_WALLET_KEY` from your secret store and repeat with `--execute`. It must match `GET /v1/me`'s
wallet. The stake and minimum gross payout above are examples; choose your own amounts and price limit.
The example signs only the terms of an eligible matching quote at or above that limit.

The script persists each command before sending it, using an atomic file replacement with restrictive
permissions. `entry.json` contains signatures with financial authority. Keep it private, do not commit it,
and keep it until the command has a known outcome. Do not run concurrent trading processes for the account.
The file lock prevents two processes from using the same journal, but cannot lock another journal or app.

```bash
.venv/bin/python examples/hyperliquid/python_entry.py --environment staging resume --state entry.json
```

Resume never signs again. A restart before signing cancels the RFQ. A saved accept is replayed with its
original key and body. If replay does not resolve it, the script reads the acceptance and fences a delayed
accept with RFQ cancellation before treating a missing acceptance as final. `UNKNOWN` operations remain
pending. A failed read stops with the journal intact; run resume after resolving the reported issue.

The example uses current HyperEVM wallet and vault cash only. It does not bridge HyperCore, cash out,
withdraw, or place native orders. The TypeScript SDK provides those flows. It is an execution example,
not a price model or a production trading system.

`signing-vectors.json` contains offline encoding fixtures with a synthetic vault domain. They check both
the quote and acceptance primary types, sell-back, cash-out transfer and exit. Expected hashes/signatures
come from the contract's known-answer vectors; the verifier uses an independent Python EIP-712 encoder.
No live credentials or private keys are included.

Run the offline command, price, funding and recovery tests with:

```bash
.venv/bin/python -m unittest discover -s examples/hyperliquid -p 'test_*.py' -v
```
