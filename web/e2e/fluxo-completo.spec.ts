import { expect, test } from "@playwright/test";

/**
 * Fluxo ponta a ponta no hub real: setup do admin → criação de agentes
 * → geração de chave → conversa via painel (perspectiva + envio).
 * Os testes são sequenciais — o banco é zerado uma vez no início do run.
 */
test.describe.configure({ mode: "serial" });

test("setup do administrador no primeiro acesso", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Criar conta de administrador" })).toBeVisible();

  await page.getByLabel("Nome").fill("Julio Admin");
  await page.getByLabel("Email").fill("julio@example.com");
  await page.getByLabel(/Senha/).fill("senha-muito-segura-1");
  await page.getByRole("button", { name: "Criar conta admin" }).click();

  // logado: shell do app com navegação
  await expect(page.getByRole("link", { name: "Conversas" })).toBeVisible();
  await expect(page.getByText("admin")).toBeVisible();
});

test("login, criação de agentes e chave do daemon", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Email").fill("julio@example.com");
  await page.getByLabel("Senha").fill("senha-muito-segura-1");
  await page.getByRole("button", { name: "Entrar" }).click();

  await page.getByRole("link", { name: "Meus agentes" }).click();

  // dois agentes para conversarem entre si
  for (const [slug, display] of [
    ["backend-julio", "Backend do Julio"],
    ["mobile-eduardo", "Mobile do Eduardo"],
  ] as const) {
    await page.getByLabel(/Slug/).fill(slug);
    await page.getByLabel("Nome de exibição").fill(display);
    await page.getByRole("button", { name: "Criar", exact: true }).click();
    await expect(page.getByRole("heading", { name: slug })).toBeVisible();
  }

  // chave exibida uma única vez, com prefixo amp_
  await page
    .locator("section", { hasText: "backend-julio" })
    .getByRole("button", { name: "Gerar chave" })
    .first()
    .click();
  await expect(page.getByText(/^amp_[0-9a-f]{64}$/)).toBeVisible();
});

test("conversa pelo painel: perspectiva, envio e bolha pendente", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Email").fill("julio@example.com");
  await page.getByLabel("Senha").fill("senha-muito-segura-1");
  await page.getByRole("button", { name: "Entrar" }).click();

  // perspectiva selecionada automaticamente (primeiro agente meu)
  await expect(page.getByLabel("Conversando como")).toHaveValue("backend-julio");

  // seleciona o parceiro e envia
  await page.getByRole("button", { name: /mobile-eduardo/ }).click();
  const composer = page.getByPlaceholder(/Mensagem para mobile-eduardo/);
  await composer.fill("Existe endpoint de reset de senha?");
  await page.getByRole("button", { name: "Enviar" }).click();

  // bolha aparece; destinatário offline → pendente
  await expect(page.getByText("Existe endpoint de reset de senha?")).toBeVisible();
  await expect(page.getByText(/pendente/)).toBeVisible();

  // histórico persiste após recarregar
  await page.reload();
  await page.getByRole("button", { name: /mobile-eduardo/ }).click();
  await expect(page.getByText("Existe endpoint de reset de senha?")).toBeVisible();
});

test("agente offline aparece com presença offline na sidebar", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Email").fill("julio@example.com");
  await page.getByLabel("Senha").fill("senha-muito-segura-1");
  await page.getByRole("button", { name: "Entrar" }).click();

  const entry = page.getByRole("button", { name: /mobile-eduardo/ });
  await expect(entry.getByLabel("offline")).toBeVisible();
});
