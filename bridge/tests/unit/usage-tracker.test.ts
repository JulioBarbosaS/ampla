import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import fc from "fast-check";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DailyUsageTracker, type UsageDelta } from "../../src/daemon/usage-tracker.js";

let dir: string;
const DAY1 = Date.UTC(2026, 5, 11, 12, 0, 0); // a fixed noon
const DAY2 = DAY1 + 24 * 3_600_000; // +24h ⇒ a different local calendar day

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "amp-usage-"));
});
afterEach(() => rmSync(dir, { recursive: true, force: true }));

function tracker(now: () => number) {
  return new DailyUsageTracker(join(dir, "usage.json"), now);
}

describe("DailyUsageTracker", () => {
  it("accumulates tokens and cost within the day", () => {
    const t = tracker(() => DAY1);
    t.add({ input_tokens: 100, output_tokens: 20, cost_usd: 0.01 });
    t.add({ input_tokens: 5, output_tokens: 5, cost_usd: 0.002 });
    expect(t.today()).toEqual({ tokens: 130, cost: 0.012 });
  });

  it("exceeds() honours each cap at the boundary; null = unlimited", () => {
    const t = tracker(() => DAY1);
    t.add({ input_tokens: 600, output_tokens: 400, cost_usd: 0.5 }); // 1000 tokens
    expect(t.exceeds(1000, null)).toBe(true); // >= cap
    expect(t.exceeds(1001, null)).toBe(false);
    expect(t.exceeds(null, 0.5)).toBe(true);
    expect(t.exceeds(null, 0.51)).toBe(false);
    expect(t.exceeds(null, null)).toBe(false); // unlimited
  });

  it("resets at the local day boundary", () => {
    let nowMs = DAY1;
    const t = tracker(() => nowMs);
    t.add({ input_tokens: 500, output_tokens: 0, cost_usd: 0.1 });
    expect(t.today().tokens).toBe(500);
    nowMs = DAY2; // next day
    expect(t.today()).toEqual({ tokens: 0, cost: 0 });
    expect(t.exceeds(100, null)).toBe(false); // budget refreshed
  });

  it("persists across a restart (a bounce can't reset the budget mid-day)", () => {
    const path = join(dir, "persist.json");
    const a = new DailyUsageTracker(path, () => DAY1);
    a.add({ input_tokens: 300, output_tokens: 200, cost_usd: 0.3 });
    // a fresh tracker on the same file, same day, sees the accumulated spend
    const b = new DailyUsageTracker(path, () => DAY1);
    expect(b.today()).toEqual({ tokens: 500, cost: 0.3 });
  });

  it("property: same-day totals equal the sum of all deltas added", () => {
    const delta: fc.Arbitrary<UsageDelta> = fc.record({
      input_tokens: fc.integer({ min: 0, max: 10_000 }),
      output_tokens: fc.integer({ min: 0, max: 10_000 }),
      cost_usd: fc.integer({ min: 0, max: 1000 }).map((c) => c / 1000),
    });
    let n = 0;
    fc.assert(
      fc.property(fc.array(delta, { maxLength: 30 }), (deltas) => {
        // a fresh file per run — the property would otherwise reload the prior
        // run's persisted totals from the shared path
        const t = new DailyUsageTracker(join(dir, `prop-${n++}.json`), () => DAY1);
        for (const d of deltas) t.add(d);
        const tokens = deltas.reduce(
          (s, d) => s + (d.input_tokens ?? 0) + (d.output_tokens ?? 0),
          0,
        );
        const cost = deltas.reduce((s, d) => s + (d.cost_usd ?? 0), 0);
        expect(t.today().tokens).toBe(tokens);
        expect(t.today().cost).toBeCloseTo(cost, 6);
      }),
    );
  });
});
