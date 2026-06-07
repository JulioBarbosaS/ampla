/**
 * Property-based tests (fast-check) — invariantes para qualquer entrada.
 *
 * Secret-filter: segredos construídos por geração DEVEM ser detectados
 * em qualquer contexto ao redor (a propriedade que 8 exemplos fixos não dão).
 * Protocolo: round-trip de mensagem sobrevive a qualquer corpo.
 */

import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { scanForSecrets } from "../../src/daemon/secret-filter.js";
import { parseServerFrame, type WireMessage } from "../../src/shared/protocol.js";

const hexChar = fc.constantFrom(..."0123456789abcdef");
const hex = (n: number) => fc.string({ unit: hexChar, minLength: n, maxLength: n });

/** Texto "inocente" ao redor do segredo (sem chance de formar padrão). */
const surrounding = fc.string({
  unit: fc.constantFrom(..."abcdefghijklmnopqrstuvwxyz ÁÉÍãç.,!?\n"),
  maxLength: 80,
});

describe("secret-filter: segredos gerados são SEMPRE detectados", () => {
  it("chave de agente Ampla em qualquer contexto", () => {
    fc.assert(
      fc.property(hex(64), surrounding, surrounding, (key, before, after) => {
        const result = scanForSecrets(`${before} amp_${key} ${after}`);
        expect(result.clean).toBe(false);
      }),
    );
  });

  it("AWS access key em qualquer contexto", () => {
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

  it("connection string com credenciais em qualquer contexto", () => {
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

  it("atribuição de variável de segredo em qualquer contexto", () => {
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

describe("protocolo: round-trip para qualquer mensagem", () => {
  const wireMessageArb: fc.Arbitrary<WireMessage> = fc.record({
    id: fc.integer({ min: 1, max: 2 ** 31 }),
    from: fc.constant("mobile-eduardo"),
    to: fc.constant("backend-julio"),
    body: fc.string({ minLength: 1, maxLength: 2000 }), // unicode arbitrário
    type: fc.constantFrom("request", "response", "notification", "task", "alert", "status", "ack"),
    priority: fc.constantFrom("urgent", "high", "normal", "low"),
    group: fc.option(fc.constantFrom("@all", "@frontend-team"), { nil: null }),
    thread_id: fc.option(fc.integer({ min: 1, max: 2 ** 31 }), { nil: null }),
    in_reply_to: fc.option(fc.integer({ min: 1, max: 2 ** 31 }), { nil: null }),
    created_at: fc.constant("2026-06-06T12:00:00Z"),
    delivered_at: fc.constant(null),
    expires_at: fc.constant(null),
  });

  it("message frame serializa → parseia → idêntico", () => {
    fc.assert(
      fc.property(wireMessageArb, (message) => {
        const frame = parseServerFrame(JSON.stringify({ type: "message", message }));
        expect(frame).toEqual({ type: "message", message });
      }),
    );
  });

  it("frames corrompidos nunca lançam — retornam null", () => {
    fc.assert(
      fc.property(fc.string({ maxLength: 500 }), (garbage) => {
        expect(() => parseServerFrame(garbage)).not.toThrow();
      }),
    );
  });
});
