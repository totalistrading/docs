// Check the slip before creating an RFQ. The venue checks eligibility again at admission.
export async function validateLegs(legs, readMarket) {
  if (!Array.isArray(legs) || !legs.length) throw new Error("Choose at least one leg.");
  let previous = -1n;
  for (const leg of legs) {
    if (!leg || typeof leg !== "object" || Array.isArray(leg)
      || Object.keys(leg).sort().join(",") !== "outcome_id,side"
      || !["YES", "NO"].includes(leg.side)) {
      throw new Error("Each leg needs an outcome_id and a YES or NO side.");
    }
    if (typeof leg.outcome_id !== "string" || !/^(0|[1-9][0-9]*)$/.test(leg.outcome_id)) {
      throw new Error("Outcome IDs must be canonical decimal strings.");
    }
    const id = BigInt(leg.outcome_id);
    if (id > 0xffffffffn || id <= previous) {
      throw new Error("Use unique uint32 outcome IDs in numeric ascending order.");
    }
    previous = id;
  }

  const yesQuestions = new Set();
  for (const leg of legs) {
    const market = await readMarket(leg.outcome_id);
    if (market.outcome_id !== leg.outcome_id || market.state !== "ACTIVE"
      || market.eligibility?.state !== "ENABLED" || market.combo?.state !== "OPEN") {
      throw new Error(`Outcome ${leg.outcome_id} does not currently admit RFQ entries.`);
    }
    if (leg.side === "YES" && market.native_question_id != null) {
      if (yesQuestions.has(market.native_question_id)) {
        throw new Error("Two YES outcomes from the same question cannot both win.");
      }
      yesQuestions.add(market.native_question_id);
    }
  }
  return legs;
}
