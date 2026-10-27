import assert from "node:assert/strict";
import test from "node:test";
import { validateLegs } from "../market-validation.js";
import { chooseAtLeast, entrySummary } from "../quote-policy.js";

const eligible = (outcome_id, native_question_id = null) => ({
  outcome_id, native_question_id, state: "ACTIVE",
  eligibility: { state: "ENABLED" }, combo: { state: "OPEN" },
});
const mixedLegs = [{ outcome_id: "9", side: "YES" }, { outcome_id: "10", side: "NO" }];

test("same-question YES outcomes cannot become a guaranteed-losing RFQ", async () => {
  await assert.rejects(validateLegs(
    [{ outcome_id: "9", side: "YES" }, { outcome_id: "10", side: "YES" }],
    async (id) => eligible(id, "question-1"),
  ), /cannot both win/);
});

test("different sides in one question and independent YES outcomes remain eligible", async () => {
  assert.equal(await validateLegs(mixedLegs, async (id) => eligible(id, "question-1")), mixedLegs);
  const independent = [{ outcome_id: "9", side: "YES" }, { outcome_id: "10", side: "YES" }];
  assert.equal(await validateLegs(independent, async (id) => eligible(id, `question-${id}`)), independent);
});

test("invalid IDs and duplicate outcomes are rejected before any market lookup", async () => {
  const invalidSlips = [
    [],
    [{ outcome_id: "09", side: "YES" }],
    [{ outcome_id: "4294967296", side: "YES" }],
    [{ outcome_id: "10", side: "NO" }, { outcome_id: "9", side: "YES" }],
    [{ outcome_id: "9", side: "YES" }, { outcome_id: "9", side: "NO" }],
    [{ outcome_id: "9", side: "MAYBE" }],
  ];
  for (const legs of invalidSlips) {
    let reads = 0;
    await assert.rejects(validateLegs(legs, async (id) => { reads++; return eligible(id); }));
    assert.equal(reads, 0);
  }
});

test("inactive, stale, ineligible and closed markets stop an entry", async () => {
  const unavailable = [
    { state: "RESOLVED" },
    { eligibility: { state: "DISABLED", reason: "STALE_REFERENCE" } },
    { eligibility: { state: "UNKNOWN" } },
    { combo: { state: "CLOSED" } },
  ];
  for (const state of unavailable) {
    await assert.rejects(validateLegs(mixedLegs, async (id) => ({ ...eligible(id), ...state })), /does not currently admit/);
  }
});

test("a market response for another outcome cannot validate the requested slip", async () => {
  await assert.rejects(validateLegs(mixedLegs, async () => eligible("11")), /does not currently admit/);
});

const now = Date.UTC(2026, 9, 21);
const quote = (payout, seconds) => ({
  kind: "ENTRY", entry: { payout }, accept_before: new Date(now + seconds * 1000).toISOString(),
});

test("the chooser never accepts a quote below the user's gross payout floor", () => {
  const choose = chooseAtLeast(10_000_000n);
  assert.equal(choose([quote("9999999", 15)], now), undefined);
  const floor = quote("10000000", 15);
  assert.equal(choose([floor], now), floor);
});

test("the chooser takes the best acceptable quote using the supplied venue clock", () => {
  const choose = chooseAtLeast(10_000_000n);
  const best = quote("15000000", 15);
  assert.equal(choose([quote("11000000", 15), best, quote("20000000", -1)], now), best);
  assert.equal(choose([best], now + 15_000), undefined);
});

test("the pre-signing display computes net full-win return from the actual signed fee terms", () => {
  const summary = entrySummary({ primaryType: "TakerAccept", message: {
    stake: 3_000_000n, payout: 9_180_000n, feeBps: 100, takerFeeBps: 20,
  } });
  assert.match(summary, /stake 3\.000000 USDC/);
  assert.match(summary, /gross payout 9\.180000 USDC/);
  assert.match(summary, /full win pays 9\.118140 USDC after fees/);
  assert.equal(entrySummary({ primaryType: "ReceiveWithAuthorization" }), undefined);
});
