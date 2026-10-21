# Totalis frontend example

Sign in with an already admitted EOA, open an RFQ position and recover a saved entry after a reload. The example
uses the public npm SDK and defaults to staging. It never asks for an API key, private key or partner server key.

## Run locally

Use Node 22 or later. Ask Totalis to register `https://totalis.localhost:3443` as your staging origin and issue a
public browser key. Admit your test wallet on your partner server first. Existing accounts need no new admission.
See [partner onboarding](https://docs.totalis.trade/hyperliquid/build/partner-frontend#onboard-a-user).

From this directory:

```bash
npm install
cp .env.example .env.local
mkdir -p certs
mkcert -install
mkcert -key-file certs/dev-key.pem -cert-file certs/dev.pem totalis.localhost
npm run dev
```

Install [mkcert](https://github.com/FiloSottile/mkcert) first if it is not available. Put your public `tpb_` key in
`.env.local`, then open `https://totalis.localhost:3443`. If that origin is taken, register your own name and update
`vite.config.js` and the certificate command together.

Connect an injected wallet, select HyperEVM testnet if prompted, then connect again. Read current eligible market
IDs from staging `GET /v1/markets?eligibility=ENABLED`; replace the sample legs before trading. Fund the wallet
with staging USDC ([staging setup](https://docs.totalis.trade/hyperliquid/build/staging#testnet-usdc)).

Before creating an RFQ, the example checks canonical unique outcome IDs in numeric order, refreshes each
market's eligibility and rejects two YES outcomes from the same question. Eligibility can still change before
admission.

Choose your own stake and minimum gross payout in atomic USDC. The entry takes the best quote meeting that
minimum through `openPosition`; if none arrives, it times out without an acceptance. The signer adapter displays
the actual selected gross payout and full-win return after fees before the wallet prompt. Review those terms
before signing. Only a committed operation opens the position. The example funds from HyperEVM wallet cash or free vault cash.
It does not bridge HyperCore funds. For a slip that shows every live quote and lets the user choose, use
`watchQuotes`, `signEntry` and `sendAcceptance` as described in
[SDK trading](https://docs.totalis.trade/hyperliquid/sdk/trading#watch-quotes-yourself).

## Verify recovery

`onSigned` saves each signed record in local storage before the SDK sends it. Refresh after signing, reconnect
the same wallet and press **Recover saved entry**. The saved record is removed only after a terminal outcome.
An account or chain change closes the client and disables trading until sign-in completes again.

The example serializes actions in one tab. A production app must coordinate tabs and other bots using the same
wallet, manage its session storage and render every account/operation status. A lost answer or abort can still
execute. Recover the existing record before allowing another trade.

`npm test` checks slip validation, the minimum payout, venue deadlines and the displayed net return offline.
`npm run build` checks the browser bundle. Neither command needs credentials or makes financial API calls. Running the
app and pressing **Request quotes and sign** submits a real staging trade with test funds. Selecting production
in `.env.local` uses production credentials and real funds.
