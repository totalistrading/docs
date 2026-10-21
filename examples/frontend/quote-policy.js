import { bestQuote, netPayout } from "@totalis/hip4-client";

export function chooseAtLeast(minimumPayout) {
  const chooseBest = bestQuote();
  return (quotes, serverNowMs) => chooseBest(
    quotes.filter((quote) => BigInt(quote.entry.payout) >= minimumPayout), serverNowMs,
  );
}

function usdc(amount) {
  const value = BigInt(amount);
  const fraction = (value % 1_000_000n).toString().padStart(6, "0");
  return `${value / 1_000_000n}.${fraction}`;
}

// Read the actual signed terms, not a quote that may have changed on screen.
export function entrySummary(typedData) {
  if (typedData.primaryType !== "TakerAccept") return undefined;
  const message = typedData.message;
  const terms = {
    stake: String(message.stake), payout: String(message.payout),
    fee_bps: Number(message.feeBps), taker_fee_bps: Number(message.takerFeeBps),
  };
  return `Selected quote: stake ${usdc(terms.stake)} USDC, gross payout ${usdc(terms.payout)} USDC. `
    + `A full win pays ${usdc(netPayout(terms))} USDC after fees. Review the exact quote in your wallet before signing.`;
}
