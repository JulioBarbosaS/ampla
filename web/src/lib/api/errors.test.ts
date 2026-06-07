import { describe, expect, it } from "vitest";
import { ApiError } from "./client";
import { authErrorMessage } from "./errors";

describe("authErrorMessage", () => {
  it("401 usa a mensagem específica da tela quando fornecida", () => {
    expect(
      authErrorMessage(new ApiError(401, "Unauthorized"), {
        unauthorized: "E-mail ou senha incorretos.",
      }),
    ).toBe("E-mail ou senha incorretos.");
  });

  it("429 vira aviso de muitas tentativas", () => {
    expect(authErrorMessage(new ApiError(429, "rate limited"))).toMatch(/Muitas tentativas/);
  });

  it("403 vira aviso de permissão", () => {
    expect(authErrorMessage(new ApiError(403, "x"))).toMatch(/permissão/);
  });

  it("422 mantém a mensagem específica do hub", () => {
    expect(authErrorMessage(new ApiError(422, "Convite inválido ou expirado."))).toBe(
      "Convite inválido ou expirado.",
    );
  });

  it("401 sem override cai na mensagem do hub", () => {
    expect(authErrorMessage(new ApiError(401, "Sessão expirada."))).toBe("Sessão expirada.");
  });

  it("erro genérico não-ApiError tem fallback", () => {
    expect(authErrorMessage("boom")).toMatch(/Algo deu errado/);
  });
});
