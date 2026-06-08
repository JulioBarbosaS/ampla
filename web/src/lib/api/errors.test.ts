import { describe, expect, it } from "vitest";
import { ApiError } from "./client";
import { authErrorMessage } from "./errors";

describe("authErrorMessage", () => {
  it("401 uses the screen-specific message when provided", () => {
    expect(
      authErrorMessage(new ApiError(401, "Unauthorized"), {
        unauthorized: "E-mail ou senha incorretos.",
      }),
    ).toBe("E-mail ou senha incorretos.");
  });

  it("429 becomes a too-many-attempts warning", () => {
    expect(authErrorMessage(new ApiError(429, "rate limited"))).toMatch(/Muitas tentativas/);
  });

  it("403 becomes a permission warning", () => {
    expect(authErrorMessage(new ApiError(403, "x"))).toMatch(/permissão/);
  });

  it("422 keeps the hub-specific message", () => {
    expect(authErrorMessage(new ApiError(422, "Convite inválido ou expirado."))).toBe(
      "Convite inválido ou expirado.",
    );
  });

  it("401 without override falls back to the hub message", () => {
    expect(authErrorMessage(new ApiError(401, "Sessão expirada."))).toBe("Sessão expirada.");
  });

  it("generic non-ApiError error has a fallback", () => {
    expect(authErrorMessage("boom")).toMatch(/Algo deu errado/);
  });
});
