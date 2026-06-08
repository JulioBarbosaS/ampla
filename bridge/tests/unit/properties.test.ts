/**
 * Property-based tests (fast-check) — invariants for any input.
 *
 * Secret-filter: secrets built by generation MUST be detected
 * in any surrounding context (the property that 8 fixed examples don't give).
 * Protocol: a message round-trip survives any body.
 */

import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { scanForSecrets } from "../../src/daemon/secret-filter.js";
import { parseServerFrame, type WireMessage } from "../../src/shared/protocol.js";

const hexChar = fc.constantFrom(..."0123456789abcdef");
const hex = (n: number) => fc.string({ unit: hexChar, minLength: n, maxLength: n });

/** "Innocent" text surrounding the secret (no chance of forming a pattern). */
const surrounding = fc.string({
  unit: fc.constantFrom(..."abcdefghijklmnopqrstuvwxyz ÁÉÍãç.,!?\n"),
  maxLength: 80,
});

describe("secret-filter: generated secrets are ALWAYS detected", () => {
  it("Ampla agent key in any context", () => {
    fc.assert(
      fc.property(hex(64), surrounding, surrounding, (key, before, after) => {
        const result = scanForSecrets(`${before} amp_${key} ${after}`);
        expect(result.clean).toBe(false);
      }),
    );
  });

  it("AWS access key in any context", () => {
    const awsTail = fc.string({
      unit: fc.constantFrom(..."ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"),
      minLength: 16,
      maxLength: 16,
    });
    fc.assert(
      fc.property(awsTail, surrounding, surrounding, (tail, before, after) => {
        expect(scanForSecrets(`${before} AKIA${tail} ${after}`).clean).toBe(false);
      }),
    );
  });

  it("connection string with credentials in any context", () => {
    const word = fc.string({
      unit: fc.constantFrom(..."abcdefghijklmnopqrstuvwxyz0123456789"),
      minLength: 1,
      maxLength: 20,
    });
    const scheme = fc.constantFrom("postgres", "postgresql", "mysql", "mongodb", "redis", "amqp");
    fc.assert(
      fc.property(scheme, word, word, surrounding, (proto, user, pass, before) => {
        const text = `${before} ${proto}://${user}:${pass}@db.interno:5432/prod`;
        expect(scanForSecrets(text).clean).toBe(false);
      }),
    );
  });

  it("secret variable assignment in any context", () => {
    const name = fc.constantFrom("PASSWORD", "SECRET", "TOKEN", "API_KEY", "PRIVATE_KEY");
    const value = fc.string({
      unit: fc.constantFrom(..."abcdefghijklmnopqrstuvwxyz0123456789!@#"),
      minLength: 1,
      maxLength: 30,
    });
    fc.assert(
      fc.property(name, value, surrounding, (varName, varValue, after) => {
        expect(scanForSecrets(`DB_${varName}=${varValue}\n${after}`).clean).toBe(false);
      }),
    );
  });
});

describe("protocol: round-trip for any message", () => {
  const wireMessageArb: fc.Arbitrary<WireMessage> = fc.record({
    id: fc.integer({ min: 1, max: 2 ** 31 }),
    from: fc.constant("mobile-eduardo"),
    to: fc.constant("backend-julio"),
    body: fc.string({ minLength: 1, maxLength: 2000 }), // arbitrary unicode
    type: fc.constantFrom("request", "response", "notification", "task", "alert", "status", "ack"),
    priority: fc.constantFrom("urgent", "high", "normal", "low"),
    group: fc.option(fc.constantFrom("@all", "@frontend-team"), { nil: null }),
    thread_id: fc.option(fc.integer({ min: 1, max: 2 ** 31 }), { nil: null }),
    in_reply_to: fc.option(fc.integer({ min: 1, max: 2 ** 31 }), { nil: null }),
    created_at: fc.constant("2026-06-06T12:00:00Z"),
    delivered_at: fc.constant(null),
    expires_at: fc.constant(null),
  });

  it("message frame serializes → parses → identical", () => {
    fc.assert(
      fc.property(wireMessageArb, (message) => {
        const frame = parseServerFrame(JSON.stringify({ type: "message", message }));
        expect(frame).toEqual({ type: "message", message });
      }),
    );
  });

  it("corrupted frames never throw — they return null", () => {
    fc.assert(
      fc.property(fc.string({ maxLength: 500 }), (garbage) => {
        expect(() => parseServerFrame(garbage)).not.toThrow();
      }),
    );
  });
});
