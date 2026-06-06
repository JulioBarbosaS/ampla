import { describe, expect, it } from "vitest";
import { scanForSecrets } from "../../src/daemon/secret-filter.js";

describe("scanForSecrets", () => {
  const leaks: Array<[string, string]> = [
    ["private key (PEM)", "-----BEGIN RSA PRIVATE KEY-----\nMIIE..."],
    ["AWS access key", "use AKIAIOSFODNN7EXAMPLE para o bucket"],
    ["chave de agente AMP", `a chave é amp_${"a1b2c3d4".repeat(8)}`],
    ["GitHub token", "ghp_abcdefghijklmnopqrstuvwxyz0123456789"],
    ["Anthropic API key", "sk-ant-api03-abcdefghijklmnopqrst"],
    [
      "JWT",
      "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
    ],
    ["connection string com senha", "postgres://app:supersenha@db.local:5432/prod"],
    ["atribuição de segredo (.env)", "DATABASE_PASSWORD=hunter2segura"],
  ];

  it.each(leaks)("detecta %s", (name, text) => {
    const result = scanForSecrets(text);
    expect(result.clean).toBe(false);
    expect(result.matches).toContain(name);
  });

  it("não bloqueia resposta técnica legítima", () => {
    const text = [
      "Sim, existe: POST /api/v1/auth/password-reset.",
      "Recebe {email} e envia token por email. Veja app/api/routes/auth.py:42.",
      "O serviço usa AuthService.reset_password() com expiração de 30 min.",
      "Exemplo: curl -X POST http://localhost:8000/api/v1/auth/password-reset",
    ].join("\n");
    expect(scanForSecrets(text)).toEqual({ clean: true, matches: [] });
  });

  it("não bloqueia menção a NOMES de variáveis sem valor", () => {
    const text =
      "Configure DATABASE_PASSWORD e JWT_SECRET no seu .env (valores com o time de infra).";
    expect(scanForSecrets(text).clean).toBe(true);
  });
});
