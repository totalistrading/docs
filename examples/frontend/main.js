import { createClient, createTotalis, normalizeError, unwrap } from "@totalis/hip4-client";
import { signInWithWallet, signOutWallet } from "@totalis/hip4-client/wallet-session";
import { validateLegs } from "./market-validation.js";
import { chooseAtLeast, entrySummary } from "./quote-policy.js";
import { toTotalisSigner } from "@totalis/hip4-client/signer";

const environment = import.meta.env.VITE_TOTALIS_ENVIRONMENT ?? "staging";
const partnerKey = import.meta.env.VITE_TOTALIS_PARTNER_KEY;
const $ = (id) => document.getElementById(id);
const show = (message) => { $("status").textContent = message; };
const provider = window.ethereum;
let current;
let busy = false;
let generation = 0;

$("environment").textContent = `Environment: ${environment}. Use current eligible market IDs from GET /v1/markets.`;

// The complete record contains its wallet, chain, vault and acceptance ID.
const prefix = (address) => `totalis:entry:${environment}:${address.toLowerCase()}:`;
const pending = (address) => Object.keys(localStorage)
  .filter((key) => key.startsWith(prefix(address)))
  .map((key) => ({ key, record: JSON.parse(localStorage.getItem(key)) }));
const save = async (record) => {
  const key = `${prefix(record.account)}${record.chainId}:${record.vault}:${record.acceptanceId}`;
  localStorage.setItem(key, JSON.stringify(record));
};
const clear = (record) => {
  const key = `${prefix(record.account)}${record.chainId}:${record.vault}:${record.acceptanceId}`;
  localStorage.removeItem(key);
};

function render() {
  $("connect").disabled = busy || !provider;
  $("disconnect").disabled = !current;
  $("open").disabled = busy || !current;
  $("recover").disabled = busy || !current;
}

function disconnect(message = "Disconnected. Saved entries remain available for recovery.") {
  generation++;
  current?.controller.abort();
  current?.totalis.close();
  current = undefined;
  show(message);
  render();
}

async function run(action) {
  if (busy) return;
  busy = true;
  render();
  try {
    await action();
  } catch (error) {
    const failure = normalizeError(error);
    const detail = failure.mayStillRun
      ? "The outcome is unknown. Reconnect the same wallet and recover its saved entry before trying another trade."
      : failure.message;
    show(`${failure.code}: ${detail}${failure.requestId ? ` Request ID: ${failure.requestId}` : ""}`);
  } finally {
    busy = false;
    render();
  }
}

async function finish(client, result, record) {
  if (result.operationId) {
    show("Maker confirmed. Waiting for the operation to commit.");
    const operation = await client.totalis.waitForOperation(result.operationId, client.controller.signal);
    clear(record);
    show(operation.status === "COMMITTED" ? `Position opened: ${result.positionId}` : `Nothing traded: ${operation.status}. Refresh balances before retrying.`);
  } else if (result.status !== "PENDING_CONFIRM") {
    clear(record);
    show(`Acceptance ended: ${result.status}.`);
  } else {
    show("Confirmation is pending. Keep the saved entry and recover it again.");
  }
}

$("connect").onclick = () => run(async () => {
  disconnect();
  const connection = generation;
  if (!["staging", "production"].includes(environment)) throw new Error("Choose staging or production.");
  if (!partnerKey?.startsWith("tpb_")) throw new Error("Set your public tpb_ browser key in .env.local.");
  await provider.request({ method: "eth_requestAccounts" });
  const deployment = unwrap(await createClient(environment).GET("/v1/deployment"));
  const expectedChain = `0x${BigInt(deployment.chain_id).toString(16)}`;
  if (BigInt(await provider.request({ method: "eth_chainId" })) !== BigInt(expectedChain)) {
    await provider.request({ method: "wallet_switchEthereumChain", params: [{ chainId: expectedChain }] });
    // Switching the chain invalidates this attempt through chainChanged. Connect again.
    show("Chain selected. Connect and sign in again.");
    return;
  }
  const session = await signInWithWallet({ environment, partnerKey, signer: provider });
  const [selected] = await provider.request({ method: "eth_accounts" });
  if (connection !== generation || selected?.toLowerCase() !== session.address) {
    await signOutWallet({ environment, partnerKey, accessToken: session.access_token });
    throw new Error("Wallet changed during sign-in. Connect again.");
  }
  const walletSigner = toTotalisSigner(provider);
  const signer = {
    address: () => walletSigner.address(),
    signMessage: (message) => walletSigner.signMessage(message),
    signTypedData: async (typedData) => {
      const summary = entrySummary(typedData);
      if (summary) {
        show(summary);
        // Paint the selected terms before opening the wallet prompt.
        await new Promise(requestAnimationFrame);
      }
      return walletSigner.signTypedData(typedData);
    },
  };
  const totalis = createTotalis({ environment, partnerKey, accessToken: session.access_token, signer });
  current = { session, totalis, controller: new AbortController() };
  await totalis.stream.live(current.controller.signal);
  show(`Signed in as ${session.address}. Saved entries: ${pending(session.address).length}.`);
});

$("disconnect").onclick = async () => {
  const session = current?.session;
  disconnect();
  if (session) {
    try { await signOutWallet({ environment, partnerKey, accessToken: session.access_token }); }
    catch { show("Disconnected locally. The sign-out request did not complete."); }
  }
};

$("open").onclick = () => run(async () => {
  const client = current;
  if (!client) return;
  if (pending(client.session.address).length) throw new Error("Recover the saved entry before opening another.");
  const requestedLegs = JSON.parse($("legs").value);
  const stake = $("stake").value;
  const minimum = $("minimum").value;
  if (![stake, minimum].every((value) => /^[1-9][0-9]*$/.test(value))) {
    throw new Error("Enter positive integer stake and minimum gross payout in atomic USDC.");
  }
  const publicClient = createClient(environment);
  const legs = await validateLegs(requestedLegs, async (outcome_id) => unwrap(
    await publicClient.GET("/v1/markets/{outcome_id}", { params: { path: { outcome_id } } }),
  ).market);
  client.controller.signal.throwIfAborted();
  if (current !== client) throw new Error("Wallet changed. Connect again before trading.");
  const opened = await client.totalis.openPosition({
    legs, stake: BigInt(stake), choose: chooseAtLeast(BigInt(minimum)), onSigned: save, signal: client.controller.signal,
  });
  await finish(client, opened, opened.record);
});

$("recover").onclick = () => run(async () => {
  const client = current;
  if (!client) return;
  const saved = pending(client.session.address);
  if (!saved.length) { show("No saved entry for this wallet and environment."); return; }
  for (const { record } of saved) {
    const result = await client.totalis.recoverAcceptance(record, { onRecord: save });
    await finish(client, result, record);
  }
});

provider?.on?.("accountsChanged", () => disconnect("Wallet changed. Connect and sign in again."));
provider?.on?.("chainChanged", () => disconnect("Chain changed. Connect and sign in again."));
provider?.on?.("disconnect", () => disconnect());
window.addEventListener("pagehide", () => current?.totalis.close());
render();
